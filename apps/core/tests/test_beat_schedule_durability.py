"""
Beat-schedule durability contract — eliminates the "long-interval task starves
under Beat restarts" class.

Incident 2026-07-18: `capture.send_pending_capture_reminders` was reported
MISSED_RUN on the Ops Wall for DAYS while the worker had the task registered and
had executed it ZERO times (queue depth 0, OPS-1 recorder provably healthy for
~20 other tasks). Root cause: Celery Beat runs the default ``PersistentScheduler``
(no ``CELERY_BEAT_SCHEDULER``, ``django_celery_beat`` not installed) whose last-run
state lives in a shelve file on Railway's EPHEMERAL container filesystem. Every
Beat restart resets interval timers to boot, so a pure-interval task whose period
exceeds Beat's uptime-between-restarts can never complete a full interval and
starves. Crontab (absolute wall-clock) schedules fire regardless of restarts.

This contract encodes the architectural rule that removes the CLASS (not just the
capture symptom): every periodic Beat task with a period longer than
``MAX_SAFE_BEAT_INTERVAL_SECONDS`` MUST use an absolute schedule (crontab), never a
numeric/timedelta interval. It fails the moment anyone reintroduces the fragile
pattern for any task — reproducing the exact production failure at CI time.
"""
from datetime import timedelta

from django.conf import settings
from django.test import SimpleTestCase

from celery.schedules import crontab

# Intervals at or below this recover within a single restart cycle and are safe.
# Above it, a pure-interval task can be starved by frequent Beat restarts on
# ephemeral storage, so an absolute (crontab) schedule is required.
MAX_SAFE_BEAT_INTERVAL_SECONDS = 1800  # 30 min


def _fragile_interval_seconds(sched):
    """Return the period in seconds IF ``sched`` is a plain numeric/timedelta
    interval (the restart-fragile kind), else None (crontab/solar → robust)."""
    if isinstance(sched, bool):
        return None
    if isinstance(sched, (int, float)):
        return float(sched)
    if isinstance(sched, timedelta):
        return sched.total_seconds()
    # crontab, solar, and any other absolute schedule object are restart-robust.
    return None


class BeatScheduleDurabilityContractTest(SimpleTestCase):
    def test_no_long_interval_beat_tasks(self):
        """The CLASS check: no monitored Beat task uses a fragile long interval."""
        offenders = []
        for name, entry in (settings.CELERY_BEAT_SCHEDULE or {}).items():
            secs = _fragile_interval_seconds(entry.get("schedule"))
            if secs is not None and secs > MAX_SAFE_BEAT_INTERVAL_SECONDS:
                offenders.append(
                    f"{name} ({entry.get('task')}) uses interval={secs}s "
                    f"> {MAX_SAFE_BEAT_INTERVAL_SECONDS}s — must be crontab"
                )
        self.assertEqual(
            offenders, [],
            "Long-interval Beat tasks starve under Beat restarts on ephemeral "
            "storage (incident 2026-07-18). Convert these to an absolute crontab "
            "schedule:\n  - " + "\n  - ".join(offenders),
        )

    def test_capture_reminders_is_crontab(self):
        """The specific regression: the incident task must be absolute, not interval."""
        entry = settings.CELERY_BEAT_SCHEDULE["capture-pending-reminders-hourly"]
        self.assertEqual(entry["task"], "capture.send_pending_capture_reminders")
        self.assertIsInstance(
            entry["schedule"], crontab,
            "capture.send_pending_capture_reminders must use a crontab schedule "
            "(restart-robust), not a numeric interval (starves — incident 2026-07-18).",
        )

    def test_detector_reproduces_the_production_failure(self):
        """The checker MUST flag the exact pre-fix condition (3600.0 interval)."""
        # The failure as it existed in production before the fix.
        self.assertEqual(_fragile_interval_seconds(3600.0), 3600.0)
        self.assertGreater(_fragile_interval_seconds(3600.0), MAX_SAFE_BEAT_INTERVAL_SECONDS)
        # A timedelta of the same period is equally fragile.
        self.assertGreater(
            _fragile_interval_seconds(timedelta(hours=1)), MAX_SAFE_BEAT_INTERVAL_SECONDS
        )
        # An absolute crontab schedule is robust — never flagged.
        self.assertIsNone(_fragile_interval_seconds(crontab(minute=0)))
        # Short intervals (the cycle drivers / keepalive) are safe — never flagged.
        self.assertLessEqual(_fragile_interval_seconds(300.0), MAX_SAFE_BEAT_INTERVAL_SECONDS)
