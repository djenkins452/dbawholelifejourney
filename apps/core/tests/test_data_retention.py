"""
Telemetry retention (apps/core/data_retention.py).

Proves: each policy deletes only rows past its window; history the readers
depend on survives (latest run per engine, arbitration feedback rows, anomaly
API logs, the live health-briefing snapshot); purges are bounded/resumable;
dry runs delete nothing; one table's failure never stops the others; the job
is scheduled as a crontab beat task.
"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.core import data_retention
from apps.core.ai_arbitration.models import ArbitrationDecisionLog
from apps.core.ai_observability.models import (
    DecisionRecord,
    EngineHeartbeat,
    EngineRun,
    EngineSpan,
    SystemIntegritySnapshot,
)
from apps.core.data_retention import POLICIES_BY_KEY, purge, run_retention
from apps.core.health_briefing.models import HealthBriefingSnapshot
from apps.core.models import APIRequestLog


def _ago(days=0, minutes=0):
    return timezone.now() - timedelta(days=days, minutes=minutes)


class RetentionFixtures(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="retention@example.com", password="x-test-pw-1")
        self._seq = 0

    def run_row(self, engine, days, status="ok"):
        self._seq += 1
        return EngineRun.objects.create(
            trace_id=f"t{self._seq}", engine_name=engine, phase=3, started_at=_ago(days), duration_ms=1, status=status
        )

    def heartbeat(self, days):
        return EngineHeartbeat.objects.create(engine_name="UAL", observed_at=_ago(days), status="OK")

    def integrity(self, days):
        snap = SystemIntegritySnapshot.objects.create(score=90.0, posture="OPTIMAL")
        SystemIntegritySnapshot.objects.filter(pk=snap.pk).update(created_at=_ago(days))
        return snap

    def span(self, days):
        self._seq += 1
        return EngineSpan.objects.create(
            trace_id=f"s{self._seq}", engine_name="CDCE", span_name="x", started_at=_ago(days), duration_ms=1
        )

    def decision(self, days):
        self._seq += 1
        rec = DecisionRecord.objects.create(
            trace_id=f"d{self._seq}", engine_name="UAL", decision_type="arbitration", decision="X"
        )
        DecisionRecord.objects.filter(pk=rec.pk).update(created_at=_ago(days))
        return rec

    def api_log(self, days, anomaly=False):
        self._seq += 1
        log = APIRequestLog.objects.create(
            request_id=f"r{self._seq}", method="GET", path="/api/x", ip_address="127.0.0.1",
            status_code=200, response_time_ms=5, is_anomaly=anomaly,
        )
        APIRequestLog.objects.filter(pk=log.pk).update(created_at=_ago(days))
        return log

    def arbitration(self, days, **feedback):
        row = ArbitrationDecisionLog.objects.create(
            user=self.user, dominant_scenario="steady", intervention_style="gentle", **feedback
        )
        ArbitrationDecisionLog.objects.filter(pk=row.pk).update(timestamp=_ago(days))
        return row

    def briefing(self, days=0, minutes=0):
        self._seq += 1
        gen = _ago(days, minutes)
        return HealthBriefingSnapshot.objects.create(
            briefing_id=f"{self._seq:064d}", user=self.user, generated_at=gen, composer_version="1.0.0",
            payload={"ok": True}, expires_at=gen + timedelta(seconds=1800),
        )


class PolicyWindowTests(RetentionFixtures):
    """Each policy deletes rows past its window and keeps rows inside it."""

    def assertWindow(self, key, make, model, inside_days, outside_days):
        keep = make(inside_days)
        drop = make(outside_days)
        result = purge(POLICIES_BY_KEY[key])
        self.assertTrue(result.complete)
        self.assertTrue(model.objects.filter(pk=keep.pk).exists(), f"{key}: in-window row deleted")
        self.assertFalse(model.objects.filter(pk=drop.pk).exists(), f"{key}: expired row kept")

    def test_engine_heartbeat_7d(self):
        self.assertWindow("engine_heartbeat", self.heartbeat, EngineHeartbeat, 6, 8)

    def test_integrity_snapshot_14d(self):
        self.assertWindow("system_integrity_snapshot", self.integrity, SystemIntegritySnapshot, 13, 15)

    def test_engine_span_14d(self):
        self.assertWindow("engine_span", self.span, EngineSpan, 13, 15)

    def test_decision_record_30d(self):
        self.assertWindow("decision_record", self.decision, DecisionRecord, 29, 31)

    def test_api_log_30d(self):
        self.assertWindow("api_request_log", self.api_log, APIRequestLog, 29, 31)

    def test_arbitration_30d(self):
        self.assertWindow("arbitration_decision_log", self.arbitration, ArbitrationDecisionLog, 29, 31)

    def test_health_briefing_30d(self):
        self.assertWindow("health_briefing_snapshot", lambda d: self.briefing(d), HealthBriefingSnapshot, 29, 31)

    def test_engine_run_30d_covers_weekly_starvation_scan(self):
        # 21 days = diagnostic starvation lookback for weekly engines; must survive.
        self.run_row("WIRE", 0)  # newer row, so the 21-day row is not the protected latest
        keep = self.run_row("WIRE", 21)
        drop = self.run_row("WIRE", 31)
        purge(POLICIES_BY_KEY["engine_run"])
        self.assertTrue(EngineRun.objects.filter(pk=keep.pk).exists())
        self.assertFalse(EngineRun.objects.filter(pk=drop.pk).exists())


class PreservedHistoryTests(RetentionFixtures):
    """History that readers depend on survives a purge."""

    def test_latest_run_of_stalled_engine_is_kept_so_heartbeat_stays_missed(self):
        from apps.core.ai_observability import heartbeat

        self.run_row("WIRE", 60)
        stale_latest = self.run_row("WIRE", 45)
        purge(POLICIES_BY_KEY["engine_run"])

        self.assertEqual(list(EngineRun.objects.filter(engine_name="WIRE")), [stale_latest])
        with mock.patch.object(
            heartbeat, "get_cadence_config", return_value={"WIRE": {"enabled": True, "interval": 604800, "jitter": 86400}}
        ):
            states = {hb.engine_name: hb.status for hb in heartbeat.compute_heartbeats()}
        self.assertEqual(states["WIRE"], "MISSED")  # not a silent NEVER_RUN

    def test_arbitration_feedback_rows_are_never_purged(self):
        answered = self.arbitration(200, user_response="accepted")
        scored = self.arbitration(200, outcome_score=0.8)
        plain = self.arbitration(200)
        purge(POLICIES_BY_KEY["arbitration_decision_log"])
        remaining = set(ArbitrationDecisionLog.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {answered.pk, scored.pk})
        self.assertFalse(ArbitrationDecisionLog.objects.filter(pk=plain.pk).exists())

    def test_anomaly_api_logs_kept_90_days(self):
        normal_40 = self.api_log(40)
        anomaly_60 = self.api_log(60, anomaly=True)
        anomaly_100 = self.api_log(100, anomaly=True)
        purge(POLICIES_BY_KEY["api_request_log"])
        self.assertFalse(APIRequestLog.objects.filter(pk=normal_40.pk).exists())
        self.assertTrue(APIRequestLog.objects.filter(pk=anomaly_60.pk).exists())
        self.assertFalse(APIRequestLog.objects.filter(pk=anomaly_100.pk).exists())

    def test_cos_health_briefing_slot_unchanged_by_purge(self):
        from apps.core.ai_orchestrator.cos_context import _build_health_briefing_slot

        self.briefing(days=40)
        live = self.briefing(minutes=5)
        before = _build_health_briefing_slot(self.user)
        purge(POLICIES_BY_KEY["health_briefing_snapshot"])
        after = _build_health_briefing_slot(self.user)
        self.assertIsNotNone(after)
        self.assertEqual(before["briefing_id"], live.briefing_id)
        self.assertEqual(after["briefing_id"], live.briefing_id)

    def test_ops_latest_reads_unchanged_by_purge(self):
        self.integrity(20)
        newest = self.integrity(0)
        self.heartbeat(20)
        hb = self.heartbeat(0)
        run_retention(["system_integrity_snapshot", "engine_heartbeat"])
        self.assertEqual(SystemIntegritySnapshot.objects.first().pk, newest.pk)
        self.assertEqual(EngineHeartbeat.objects.first().pk, hb.pk)


class BoundedExecutionTests(RetentionFixtures):
    def test_dry_run_counts_and_deletes_nothing(self):
        for _ in range(3):
            self.heartbeat(10)
        self.heartbeat(1)
        result = purge(POLICIES_BY_KEY["engine_heartbeat"], dry_run=True)
        self.assertEqual(result.eligible, 3)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(EngineHeartbeat.objects.count(), 4)

    def test_batch_cap_is_partial_then_resumes(self):
        for _ in range(5):
            self.heartbeat(10)
        policy = POLICIES_BY_KEY["engine_heartbeat"]
        first = purge(policy, batch_size=2, max_batches=1)
        self.assertEqual((first.deleted, first.complete), (2, False))
        second = purge(policy, batch_size=2)
        self.assertEqual((second.deleted, second.complete), (3, True))
        self.assertFalse(EngineHeartbeat.objects.exists())

    def test_deadline_stops_cleanly(self):
        self.heartbeat(10)
        result = purge(POLICIES_BY_KEY["engine_heartbeat"], deadline=0)
        self.assertFalse(result.complete)
        self.assertEqual(EngineHeartbeat.objects.count(), 1)

    def test_one_table_failure_does_not_stop_others_and_is_reported(self):
        self.heartbeat(10)
        real_purge = data_retention.purge

        def flaky(policy, **kw):
            if policy.key == "engine_span":
                raise RuntimeError("boom")
            return real_purge(policy, **kw)

        with mock.patch.object(data_retention, "purge", side_effect=flaky):
            results = {r.key: r for r in run_retention()}
        self.assertIn("boom", results["engine_span"].error)
        self.assertEqual(results["engine_heartbeat"].deleted, 1)

        with mock.patch.object(data_retention, "purge", side_effect=flaky):
            with self.assertRaises(CommandError):
                call_command("prune_telemetry", stdout=StringIO())

    def test_scheduled_job_raises_on_failure_so_monitor_records_it(self):
        from apps.core import jobs

        failing = data_retention.PurgeResult(key="engine_span", table="t", retention_days=14, error="boom")
        with mock.patch("apps.core.data_retention.run_retention", return_value=[failing]):
            with self.assertRaises(RuntimeError):
                jobs.prune_telemetry()


class CommandAndScheduleTests(RetentionFixtures):
    def test_legacy_commands_delegate_to_policies(self):
        old = self.api_log(40)
        recent = self.api_log(5)
        call_command("cleanup_api_logs", "--dry-run", stdout=StringIO())
        self.assertTrue(APIRequestLog.objects.filter(pk=old.pk).exists())
        call_command("cleanup_api_logs", stdout=StringIO())
        self.assertFalse(APIRequestLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(APIRequestLog.objects.filter(pk=recent.pk).exists())

    def test_list_shows_every_policy(self):
        out = StringIO()
        call_command("prune_telemetry", "--list", stdout=out)
        for key in POLICIES_BY_KEY:
            self.assertIn(key, out.getvalue())

    def test_daily_crontab_beat_entry(self):
        entry = settings.CELERY_BEAT_SCHEDULE["telemetry-retention-daily-345am-utc"]
        self.assertEqual(entry["task"], "core.prune_telemetry")
        self.assertIsInstance(entry["schedule"], crontab)

    def test_task_is_registered(self):
        import apps.core.tasks  # noqa: F401  (registers @shared_task)
        from config.celery import app

        self.assertIn("core.prune_telemetry", app.tasks)
