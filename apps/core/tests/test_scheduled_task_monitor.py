"""
OPS-1 — Scheduled Beat Task Monitor tests.

Proves the generic Beat-schedule-vs-actual-run reconciler:
  * expected cadence is derived from CELERY_BEAT_SCHEDULE (excluding the
    ISE/SAME scheduler cycles already covered by SchedulerHeartbeat),
  * runs are recorded (upsert, one row per task),
  * OK / LATE / MISSED / NEVER_RUN states compute correctly,
  * MISSED tasks produce MISSED_RUN anomaly descriptors,
  * the descriptors flow through the real SAME cycle into OpsAnomaly rows
    (the end-to-end runtime proof, not just a unit check),
  * the telemetry section summarizes freshness.

Path: apps/core/tests/test_scheduled_task_monitor.py
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_observability import scheduled_task_monitor as stm
from apps.core.ai_observability.models import OpsAnomaly, ScheduledTaskRun

# A representative subset of the OPS-1 tasks named in the documentation.
GOAL_MOMENTUM = "dashboard_v2.compute_nightly_momentum"
SOFT_DELETE = "core.cleanup_soft_deletes"
CAPTURE_RETENTION = "capture.send_expiration_reminders"
COS_KEEPALIVE = "apps.ai.tasks.cos_keepalive_task"


class MonitoredRegistryTests(TestCase):
    def setUp(self):
        stm.cache.delete(stm._CADENCE_CACHE_KEY)

    def test_registry_covers_documented_ops1_tasks(self):
        reg = stm.get_monitored_beat_tasks()
        for task in (GOAL_MOMENTUM, SOFT_DELETE, CAPTURE_RETENTION, COS_KEEPALIVE):
            self.assertIn(task, reg, f"{task} should be monitored (OPS-1)")

    def test_scheduler_cycles_excluded(self):
        reg = stm.get_monitored_beat_tasks()
        self.assertNotIn("apps.core.tasks.run_same_cycle_task", reg)
        self.assertNotIn("apps.core.tasks.run_ise_cycle_task", reg)

    def test_daily_and_weekly_cadence_estimation(self):
        reg = stm.get_monitored_beat_tasks()
        # Goal momentum runs at a fixed daily time -> ~86400s.
        self.assertEqual(reg[GOAL_MOMENTUM]["interval_seconds"], 86400)
        # Soft-delete cleanup runs weekly on Sunday -> ~604800s.
        self.assertEqual(reg[SOFT_DELETE]["interval_seconds"], 604800)
        # cos_keepalive is a 30s interval task.
        self.assertEqual(reg[COS_KEEPALIVE]["interval_seconds"], 30)

    def test_interval_number_and_crontab_helpers(self):
        from celery.schedules import crontab
        self.assertEqual(stm._crontab_interval_seconds(crontab(hour=7, minute=30)), 86400)
        self.assertEqual(
            stm._crontab_interval_seconds(crontab(hour=3, minute=0, day_of_week="sun")),
            604800,
        )


class RecordRunTests(TestCase):
    def setUp(self):
        stm.cache.delete(stm._CADENCE_CACHE_KEY)

    def test_record_upserts_single_row(self):
        stm.record_scheduled_task_run(GOAL_MOMENTUM, status="success")
        stm.record_scheduled_task_run(GOAL_MOMENTUM, status="success")
        rows = ScheduledTaskRun.objects.filter(task_name=GOAL_MOMENTUM)
        self.assertEqual(rows.count(), 1, "runs must upsert to one current-state row")

    def test_unmonitored_task_is_not_recorded(self):
        stm.record_scheduled_task_run("some.unmonitored.task", status="success")
        self.assertFalse(
            ScheduledTaskRun.objects.filter(task_name="some.unmonitored.task").exists()
        )

    def test_postrun_signal_handler_records(self):
        class _Sender:
            name = GOAL_MOMENTUM

        stm._on_task_postrun(task_id="t1", sender=_Sender(), state="SUCCESS")
        row = ScheduledTaskRun.objects.get(task_name=GOAL_MOMENTUM)
        self.assertEqual(row.status, "success")

    def test_postrun_failure_records_error(self):
        class _Sender:
            name = SOFT_DELETE

        stm._on_task_postrun(
            task_id="t2", sender=_Sender(), state="FAILURE", retval=ValueError("boom")
        )
        row = ScheduledTaskRun.objects.get(task_name=SOFT_DELETE)
        self.assertEqual(row.status, "error")
        self.assertIn("boom", row.error_message)


class StateAndMissedRunTests(TestCase):
    def setUp(self):
        stm.cache.delete(stm._CADENCE_CACHE_KEY)
        self.now = timezone.now()

    def _set_last_run(self, task_name, ran_at, status="success"):
        ScheduledTaskRun.objects.update_or_create(
            task_name=task_name,
            defaults={"ran_at": ran_at, "status": status},
        )

    def test_fresh_run_is_ok_no_anomaly(self):
        self._set_last_run(GOAL_MOMENTUM, self.now - timedelta(minutes=5))
        states = {s["task_name"]: s for s in stm.compute_scheduled_task_states(self.now)}
        self.assertEqual(states[GOAL_MOMENTUM]["status"], "OK")
        anoms = stm.detect_scheduled_task_missed_runs(self.now)
        self.assertFalse(any(a["engine_name"] == GOAL_MOMENTUM for a in anoms))

    def test_never_run_is_not_flagged_missed(self):
        states = {s["task_name"]: s for s in stm.compute_scheduled_task_states(self.now)}
        self.assertEqual(states[GOAL_MOMENTUM]["status"], "NEVER_RUN")
        anoms = stm.detect_scheduled_task_missed_runs(self.now)
        self.assertEqual(anoms, [])

    def test_stale_run_is_missed_and_flagged(self):
        # Daily task; last run 2 days ago -> well past interval + jitter.
        self._set_last_run(GOAL_MOMENTUM, self.now - timedelta(days=2))
        states = {s["task_name"]: s for s in stm.compute_scheduled_task_states(self.now)}
        self.assertEqual(states[GOAL_MOMENTUM]["status"], "MISSED")

        anoms = stm.detect_scheduled_task_missed_runs(self.now)
        match = [a for a in anoms if a["engine_name"] == GOAL_MOMENTUM]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["anomaly_type"], "MISSED_RUN")
        self.assertIn(match[0]["severity"], ("P1", "P2"))

    def test_telemetry_summarizes_states(self):
        self._set_last_run(GOAL_MOMENTUM, self.now - timedelta(minutes=5))  # OK
        self._set_last_run(SOFT_DELETE, self.now - timedelta(days=30))       # MISSED
        tel = stm.get_scheduled_tasks_telemetry(self.now)
        self.assertGreaterEqual(tel["total"], 2)
        self.assertGreaterEqual(tel["counts"]["MISSED"], 1)
        self.assertEqual(tel["status"], "MISSED")


class EndToEndSameCycleTests(TestCase):
    """Runtime proof: a stale Beat task surfaces as an OpsAnomaly via SAME."""

    def setUp(self):
        stm.cache.delete(stm._CADENCE_CACHE_KEY)

    def test_missed_beat_task_creates_opsanomaly_through_same(self):
        from apps.core.ai_observability.same_engine import run_same

        now = timezone.now()
        # Goal momentum last ran 3 days ago -> missed.
        ScheduledTaskRun.objects.update_or_create(
            task_name=GOAL_MOMENTUM,
            defaults={"ran_at": now - timedelta(days=3), "status": "success"},
        )

        run_same()

        anomaly = OpsAnomaly.objects.filter(
            anomaly_type="MISSED_RUN",
            engine_name=GOAL_MOMENTUM,
            is_active=True,
        ).first()
        self.assertIsNotNone(
            anomaly,
            "SAME cycle must create an active MISSED_RUN anomaly for the "
            "stale scheduled Beat task",
        )
        # The full task name must fit (engine_name widened to 128 for OPS-1).
        self.assertEqual(anomaly.engine_name, GOAL_MOMENTUM)
