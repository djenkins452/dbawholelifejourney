"""
Telemetry retention (apps/core/data_retention.py).

Proves: each policy deletes only rows past its window; history the readers
depend on survives (latest run per engine, arbitration feedback rows, anomaly
API logs, the live health-briefing snapshot); purges are bounded/resumable;
dry runs delete nothing; one table's failure never stops the others; the job
is scheduled as a crontab beat task; nothing is deleted unless the table is
activated; live runs cannot overlap.
"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
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
from apps.core.data_retention import POLICIES_BY_KEY, RetentionBusy, purge, run_retention
from apps.core.health_briefing.models import HealthBriefingSnapshot
from apps.core.models import APIRequestLog


def _ago(days=0, minutes=0):
    return timezone.now() - timedelta(days=days, minutes=minutes)


ALL_ON = override_settings(WLJ_TELEMETRY_RETENTION_TABLES=["all"])


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


@ALL_ON
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


@ALL_ON
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


@ALL_ON
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


class ActivationGateTests(RetentionFixtures):
    """Default deployment deletes nothing through ANY entry point."""

    def _expired_everywhere(self):
        return [self.heartbeat(10), self.api_log(40), self.decision(40), self.span(40)]

    def assertAllStillPresent(self, rows):
        for row in rows:
            self.assertTrue(type(row).objects.filter(pk=row.pk).exists(), f"{type(row).__name__} deleted while disabled")

    @override_settings(WLJ_TELEMETRY_RETENTION_TABLES=[])
    def test_nightly_job_is_a_noop_when_disabled(self):
        from apps.core import jobs

        rows = self._expired_everywhere()
        self.assertEqual(jobs.prune_telemetry(), {"status": "disabled"})
        self.assertAllStillPresent(rows)

    @override_settings(WLJ_TELEMETRY_RETENTION_TABLES=[])
    def test_commands_delete_nothing_when_disabled(self):
        rows = self._expired_everywhere()
        out = StringIO()
        call_command("prune_telemetry", stdout=out)
        call_command("cleanup_api_logs", stdout=out)
        call_command("cleanup_diagnostics", stdout=out)
        self.assertAllStillPresent(rows)
        self.assertIn("skipped (disabled", out.getvalue())

    @override_settings(WLJ_TELEMETRY_RETENTION_TABLES=[])
    def test_dry_run_works_while_disabled(self):
        self.heartbeat(10)
        results = {r.key: r for r in run_retention(["engine_heartbeat"], dry_run=True)}
        self.assertEqual(results["engine_heartbeat"].eligible, 1)

    @override_settings(WLJ_TELEMETRY_RETENTION_TABLES=["engine_heartbeat"])
    def test_only_activated_tables_are_purged(self):
        hb = self.heartbeat(10)
        log = self.api_log(40)
        results = {r.key: r for r in run_retention()}
        self.assertFalse(EngineHeartbeat.objects.filter(pk=hb.pk).exists())
        self.assertTrue(APIRequestLog.objects.filter(pk=log.pk).exists())
        self.assertEqual(results["api_request_log"].skipped, "disabled")

    @override_settings(WLJ_TELEMETRY_RETENTION_TABLES=["typo_table"])
    def test_unknown_keys_activate_nothing(self):
        hb = self.heartbeat(10)
        run_retention()
        self.assertTrue(EngineHeartbeat.objects.filter(pk=hb.pk).exists())


@ALL_ON
class RunLockTests(RetentionFixtures):
    def _hold(self, seconds_ago=0):
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock

        return SchedulerLock.objects.create(
            lock_name="telemetry_retention", locked_at=_ago(minutes=seconds_ago / 60), locked_by="other-host"
        )

    def test_live_run_refuses_while_another_holds_the_lock(self):
        hb = self.heartbeat(10)
        self._hold()
        with self.assertRaises(RetentionBusy):
            run_retention()
        self.assertTrue(EngineHeartbeat.objects.filter(pk=hb.pk).exists())
        with self.assertRaises(CommandError):
            call_command("prune_telemetry", stdout=StringIO())

    def test_nightly_job_skips_not_fails_while_manual_run_holds_lock(self):
        from apps.core import jobs

        self._hold()
        self.assertEqual(jobs.prune_telemetry(), {"status": "busy"})

    def test_stale_lock_is_taken_over_and_released(self):
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock

        self.heartbeat(10)
        self._hold(seconds_ago=3600)
        run_retention()
        self.assertFalse(EngineHeartbeat.objects.exists())
        self.assertFalse(SchedulerLock.objects.filter(lock_name="telemetry_retention").exists())

    def test_lock_released_after_normal_run(self):
        from apps.core.ai_scheduler.scheduler_models import SchedulerLock

        run_retention()
        self.assertFalse(SchedulerLock.objects.filter(lock_name="telemetry_retention").exists())

    def test_lock_check_error_fails_closed(self):
        hb = self.heartbeat(10)
        with mock.patch(
            "apps.core.ai_scheduler.scheduler_models.SchedulerLock.objects.get_or_create",
            side_effect=RuntimeError("db hiccup"),
        ):
            with self.assertRaises(RetentionBusy):
                run_retention()
        self.assertTrue(EngineHeartbeat.objects.filter(pk=hb.pk).exists())

    def test_dry_run_needs_no_lock(self):
        self._hold()
        self.heartbeat(10)
        self.assertEqual(run_retention(["engine_heartbeat"], dry_run=True)[0].eligible, 1)


class ConversationReferencedBriefingTests(RetentionFixtures):
    """A snapshot that was live during a user chat turn is the only record of
    what the assistant was told (prompts are not persisted) — kept forever."""

    def _turn(self, at, role="user"):
        from apps.ai.models import AssistantConversation, AssistantMessage

        convo = AssistantConversation.objects.create(user=self.user)
        msg = AssistantMessage.objects.create(conversation=convo, role=role, content="hi")
        AssistantMessage.objects.filter(pk=msg.pk).update(created_at=at)
        return msg

    def test_snapshot_live_during_user_turn_is_kept_regardless_of_age(self):
        referenced = self.briefing(days=200)
        self._turn(referenced.generated_at + timedelta(minutes=10))
        unreferenced = self.briefing(days=199)
        purge(POLICIES_BY_KEY["health_briefing_snapshot"])
        self.assertTrue(HealthBriefingSnapshot.objects.filter(pk=referenced.pk).exists())
        self.assertFalse(HealthBriefingSnapshot.objects.filter(pk=unreferenced.pk).exists())

    def test_turn_after_expiry_does_not_protect(self):
        snap = self.briefing(days=200)
        self._turn(snap.expires_at + timedelta(minutes=1))
        purge(POLICIES_BY_KEY["health_briefing_snapshot"])
        self.assertFalse(HealthBriefingSnapshot.objects.filter(pk=snap.pk).exists())

    def test_assistant_message_alone_does_not_protect(self):
        snap = self.briefing(days=200)
        self._turn(snap.generated_at + timedelta(minutes=10), role="assistant")
        purge(POLICIES_BY_KEY["health_briefing_snapshot"])
        self.assertFalse(HealthBriefingSnapshot.objects.filter(pk=snap.pk).exists())

    def test_another_users_turn_does_not_protect(self):
        other = get_user_model().objects.create_user(email="other-retention@example.com", password="x-test-pw-2")
        from apps.ai.models import AssistantConversation, AssistantMessage

        snap = self.briefing(days=200)
        convo = AssistantConversation.objects.create(user=other)
        msg = AssistantMessage.objects.create(conversation=convo, role="user", content="hi")
        AssistantMessage.objects.filter(pk=msg.pk).update(created_at=snap.generated_at + timedelta(minutes=5))
        purge(POLICIES_BY_KEY["health_briefing_snapshot"])
        self.assertFalse(HealthBriefingSnapshot.objects.filter(pk=snap.pk).exists())


class WeightTunerCadenceTests(RetentionFixtures):
    """The tuner fires when a user's all-time decision count is a multiple of 50
    and it has >= 10 feedback rows. A purge lowers the count, so the next firing
    lands at the next multiple of 50 of the NEW count: the interval (every 50
    decisions) is unchanged; only which decision triggers it moves. Feedback
    rows — the tuner's only input — survive the purge."""

    SCENARIO = "TIME_CRITICAL"

    def setUp(self):
        super().setUp()
        from apps.core.ai_arbitration.scenario_classifier import TIME_CRITICAL

        self.scenario = TIME_CRITICAL

    def _decide(self, n, days=0, **feedback):
        for _ in range(n):
            row = ArbitrationDecisionLog.objects.create(
                user=self.user, dominant_scenario=self.scenario, intervention_style="gentle", **feedback
            )
            if days:
                ArbitrationDecisionLog.objects.filter(pk=row.pk).update(timestamp=_ago(days))

    def _firings(self, decisions):
        from apps.core.ai_arbitration.weight_tuner import maybe_tune_weights

        fired = []
        for i in range(decisions):
            self._decide(1)
            if maybe_tune_weights(self.user):
                fired.append(ArbitrationDecisionLog.objects.filter(user=self.user).count())
        return fired

    def test_purge_shifts_phase_not_interval_and_keeps_feedback(self):
        from apps.core.ai_arbitration.models import WeightAdjustment

        self._decide(12, days=90, user_response="complied")  # feedback: never purged
        self._decide(125, days=90)  # plain history: purged
        self.assertEqual(ArbitrationDecisionLog.objects.filter(user=self.user).count(), 137)

        purge(POLICIES_BY_KEY["arbitration_decision_log"])
        self.assertEqual(ArbitrationDecisionLog.objects.filter(user=self.user).count(), 12)

        fired = self._firings(100)
        # Without the purge the count would have hit 150 and 200; now it hits 50 and 100.
        self.assertEqual(fired, [50, 100])
        self.assertEqual(fired[1] - fired[0], 50)
        self.assertTrue(WeightAdjustment.objects.filter(user=self.user, scenario=self.scenario).exists())

    def test_without_feedback_tuner_never_fires_before_or_after_purge(self):
        # Production today: 0 feedback rows, so tuning never runs either way.
        self._decide(149, days=90)
        self.assertEqual(self._firings(1), [])  # count 150, but < 10 feedback rows
        purge(POLICIES_BY_KEY["arbitration_decision_log"])
        self.assertEqual(self._firings(50), [])
