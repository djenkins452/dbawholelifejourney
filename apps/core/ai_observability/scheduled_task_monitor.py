"""
Scheduled Beat Task Monitor — OPS-1.

Generic observability for every Celery Beat scheduled task that is NOT a
registered intelligence engine (Goal Momentum, cleanup jobs, image-retention,
celebrations, digests, reminders, cos_keepalive, …).

Problem it solves
-----------------
The Ops Wall heartbeat / MISSED_RUN machinery is engine-centric: it only sees
work that writes ``EngineRun`` records via the trace-based
``log_engine_run`` decorator inside the ISE cycle. Plain Beat tasks write no
such records and have no cadence config, so a scheduled job could die silently
in production — no heartbeat, MISSED_RUN never fires. (See
``docs/WLJ_OPS_WALL_COVERAGE.md`` §4, gap OPS-1.)

How it works (the generic "Beat-schedule-vs-actual-run reconciler")
-------------------------------------------------------------------
* **Expected cadence** is derived directly from
  ``settings.CELERY_BEAT_SCHEDULE`` — no hand-maintained list. Every scheduled
  job is covered automatically, including ones added later. The two scheduler
  *cycle* tasks (SAME/ISE) are excluded because their liveness is already
  tracked via ``SchedulerHeartbeat``.
* **Actual runs** are recorded by Celery ``task_postrun`` / ``task_prerun``
  signals — no per-task code edits. Each monitored task UPSERTS one
  ``ScheduledTaskRun`` row (current state: last run time + last status),
  keeping storage bounded.
* **Reconciliation** compares expected cadence vs. last actual run and emits
  ``MISSED_RUN`` anomalies through the *existing* SAME anomaly pipeline
  (``run_same`` → ``_reconcile_anomalies``), so they appear on the Ops Wall,
  escalate, and resolve exactly like engine misses.
* A dedicated ``scheduled_tasks`` telemetry section gives positive
  visibility (freshness of every job, even while healthy).

This is deliberately separate from the engine heartbeat path so it does not
pollute engine-health / integrity / narrative or the error-spike / starvation
detectors, which key off ``EngineRun`` and the engine registry.

Project: Whole Life Journey
Path: apps/core/ai_observability/scheduled_task_monitor.py
"""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Beat tasks whose liveness is ALREADY monitored via SchedulerHeartbeat
# (ISE + SAME cycle drivers). Excluded to avoid double-coverage.
_EXCLUDED_TASK_NAMES = frozenset({
    "apps.core.tasks.run_same_cycle_task",
    "apps.core.tasks.run_ise_cycle_task",
})

_CADENCE_CACHE_KEY = "wlj:ops:beat_task_cadence"
_CADENCE_CACHE_TTL = 300  # 5 min — schedule is static per deploy

# In-process start-time stash for duration measurement (task_id -> monotonic).
# Bounded: entries are popped in postrun; a task that skips postrun leaves at
# most one stale entry, cleaned opportunistically below.
_START_TIMES = {}
_MAX_START_TIMES = 512


# =========================================================================
# EXPECTED CADENCE — derived from CELERY_BEAT_SCHEDULE
# =========================================================================


def _crontab_interval_seconds(sched):
    """
    Estimate the nominal period (seconds) of a Celery crontab schedule.

    Celery ``crontab`` exposes the parsed fields as sets: ``minute``,
    ``hour``, ``day_of_week``, ``day_of_month``, ``month_of_year``. We pick
    the coarsest restricted field to estimate how often it fires. This is an
    approximation used only to size the "is it overdue?" window — exactness
    is not required, generous jitter absorbs the slack.
    """
    try:
        minute = sched.minute
        hour = sched.hour
        dow = sched.day_of_week
        dom = sched.day_of_month

        # Restricted to specific weekday(s) -> weekly, divided by #days.
        if dow and len(dow) < 7:
            return int(round(7 * 86400 / len(dow)))
        # Restricted to specific day(s) of month -> monthly, divided.
        if dom and len(dom) < 31:
            return int(round(30 * 86400 / len(dom)))
        # Specific hour(s) each day -> daily, divided by #hours.
        if hour and len(hour) < 24:
            return int(round(86400 / len(hour)))
        # Specific minute(s) each hour -> hourly, divided by #minutes.
        if minute and len(minute) < 60:
            return int(round(3600 / len(minute)))
        return 3600
    except Exception:
        return 86400  # safe daily default


def _jitter_for(interval):
    """
    Generous late window before a task is considered MISSED.

    Beat dispatch, worker queue depth, and long-running jobs all add slack;
    a too-tight jitter would produce false MISSED_RUN alarms. We err toward
    quiet: a real missed run is still caught well before the next cycle.
    """
    if interval <= 60:
        return 60          # 30-60s tasks: allow ~1 missed tick
    if interval <= 300:
        return 240
    if interval <= 3600:
        return 1800        # hourly-ish: 30m grace
    if interval < 86400:
        return int(interval)  # sub-daily: a full interval of grace
    if interval < 604800:
        return 10800       # daily: 3h grace
    return 172800          # weekly+: 2-day grace


def get_monitored_beat_tasks():
    """
    Build the monitored-task registry from ``settings.CELERY_BEAT_SCHEDULE``.

    Returns:
        dict: task_name -> {
            "label": str,              # human label (schedule key)
            "interval_seconds": int,
            "jitter_seconds": int,
        }
    Cached ``_CADENCE_CACHE_TTL`` seconds (the schedule is static per deploy).
    """
    cached = cache.get(_CADENCE_CACHE_KEY)
    if cached is not None:
        return cached

    registry = {}
    schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}

    for key, entry in schedule.items():
        task_name = entry.get("task")
        if not task_name or task_name in _EXCLUDED_TASK_NAMES:
            continue

        sched = entry.get("schedule")
        if isinstance(sched, (int, float)):
            interval = int(sched)
        else:
            # crontab (or anything crontab-like exposing the field sets)
            interval = _crontab_interval_seconds(sched)

        registry[task_name] = {
            "label": key,
            "interval_seconds": interval,
            "jitter_seconds": _jitter_for(interval),
        }

    cache.set(_CADENCE_CACHE_KEY, registry, timeout=_CADENCE_CACHE_TTL)
    return registry


# =========================================================================
# ACTUAL RUNS — Celery signal recorders
# =========================================================================


def record_scheduled_task_run(task_name, status="success", duration_ms=0,
                              error_message="", when=None):
    """
    Upsert the current-state row for a monitored Beat task (fire-and-forget).

    Only records tasks in the monitored registry so write volume stays bounded
    to the number of scheduled jobs (~two dozen rows total).
    """
    try:
        if task_name not in get_monitored_beat_tasks():
            return

        from apps.core.ai_observability.models import ScheduledTaskRun

        ScheduledTaskRun.objects.update_or_create(
            task_name=task_name,
            defaults={
                "ran_at": when or timezone.now(),
                "status": status,
                "duration_ms": int(duration_ms or 0),
                "error_message": (error_message or "")[:500],
            },
        )
    except Exception as e:  # never let telemetry break a task
        logger.debug("ScheduledTaskRun upsert failed for %s: %s", task_name, e)


def _on_task_prerun(task_id=None, task=None, sender=None, **kwargs):
    """Stash a monotonic start time for duration measurement."""
    try:
        name = getattr(sender, "name", None) or getattr(task, "name", None)
        if not name or name not in get_monitored_beat_tasks():
            return
        if len(_START_TIMES) > _MAX_START_TIMES:
            _START_TIMES.clear()  # safety valve against unbounded growth
        if task_id:
            _START_TIMES[task_id] = time.monotonic()
    except Exception:
        pass


def _on_task_postrun(task_id=None, task=None, sender=None, state=None,
                     retval=None, **kwargs):
    """Record a monitored task's completion as current state."""
    try:
        name = getattr(sender, "name", None) or getattr(task, "name", None)
        if not name or name not in get_monitored_beat_tasks():
            return

        started = _START_TIMES.pop(task_id, None) if task_id else None
        duration_ms = int((time.monotonic() - started) * 1000) if started else 0

        status = "success" if state == "SUCCESS" else "error"
        error_message = "" if status == "success" else str(retval)[:500]

        record_scheduled_task_run(
            name, status=status, duration_ms=duration_ms,
            error_message=error_message,
        )
    except Exception as e:
        logger.debug("task_postrun recorder failed: %s", e)


_SIGNALS_CONNECTED = False


def connect_signals():
    """
    Connect the Celery task signals. Idempotent — safe to call from
    ``AppConfig.ready()`` (which can run more than once in some setups).
    """
    global _SIGNALS_CONNECTED
    if _SIGNALS_CONNECTED:
        return
    try:
        from celery.signals import task_postrun, task_prerun

        task_prerun.connect(_on_task_prerun, dispatch_uid="wlj_beat_prerun")
        task_postrun.connect(_on_task_postrun, dispatch_uid="wlj_beat_postrun")
        _SIGNALS_CONNECTED = True
        logger.info("Scheduled-task monitor: Celery signals connected (OPS-1).")
    except Exception as e:
        logger.warning("Scheduled-task monitor: signal connect failed: %s", e)


# =========================================================================
# RECONCILIATION — compute states + MISSED_RUN detection
# =========================================================================


def compute_scheduled_task_states(now=None):
    """
    Compute the current cadence state for every monitored Beat task.

    Returns:
        list[dict], each with:
            task_name, label, status (OK/LATE/MISSED/NEVER_RUN),
            interval_seconds, jitter_seconds, last_run_at (iso|None),
            next_expected_at (iso|None), lateness_seconds, last_status
    """
    from apps.core.ai_observability.models import ScheduledTaskRun

    now = now or timezone.now()
    registry = get_monitored_beat_tasks()

    # One query for all last-run rows.
    last_runs = {
        r.task_name: r
        for r in ScheduledTaskRun.objects.filter(task_name__in=registry.keys())
    }

    states = []
    for task_name, cfg in registry.items():
        interval = cfg["interval_seconds"]
        jitter = cfg["jitter_seconds"]
        run = last_runs.get(task_name)

        if run is None:
            status = "NEVER_RUN"
            next_expected_at = None
            lateness = 0
            last_run_at = None
            last_status = None
        else:
            last_run_at = run.ran_at
            last_status = run.status
            next_expected_at = last_run_at + timedelta(seconds=interval)
            deadline = next_expected_at + timedelta(seconds=jitter)
            if now <= next_expected_at:
                status = "OK"
                lateness = 0
            elif now <= deadline:
                status = "LATE"
                lateness = int((now - next_expected_at).total_seconds())
            else:
                status = "MISSED"
                lateness = int((now - next_expected_at).total_seconds())

        states.append({
            "task_name": task_name,
            "label": cfg["label"],
            "status": status,
            "interval_seconds": interval,
            "jitter_seconds": jitter,
            "last_run_at": last_run_at.isoformat() if last_run_at else None,
            "next_expected_at": (
                next_expected_at.isoformat() if next_expected_at else None
            ),
            "lateness_seconds": lateness,
            "last_status": last_status,
        })

    states.sort(key=lambda s: s["task_name"])
    return states


def detect_scheduled_task_missed_runs(now=None):
    """
    Build MISSED_RUN anomaly descriptors for overdue Beat tasks.

    Shape matches the SAME engine detectors so the descriptors flow straight
    into ``_reconcile_anomalies`` alongside engine misses. ``engine_name`` is
    the full task name (OpsAnomaly.engine_name widened to 128 for OPS-1),
    which is the stable reconciliation key.

    NEVER_RUN is intentionally NOT flagged: a task that has not run since the
    monitor was deployed is not yet proven missed (its first run may simply be
    in the future). It surfaces in telemetry as "awaiting first run".
    """
    now = now or timezone.now()
    anomalies = []

    for st in compute_scheduled_task_states(now):
        if st["status"] != "MISSED":
            continue

        minutes_late = st["lateness_seconds"] // 60
        interval_minutes = max(1, st["interval_seconds"] // 60)
        severity = "P1" if st["lateness_seconds"] > st["interval_seconds"] * 3 else "P2"

        anomalies.append({
            "anomaly_type": "MISSED_RUN",
            "severity": severity,
            "engine_name": st["task_name"],
            "summary": (
                f"Scheduled task '{st['label']}' ({st['task_name']}) missed "
                f"expected cadence — {minutes_late}m overdue "
                f"(expected every ~{interval_minutes}m)"
            ),
            "evidence": {
                "task_name": st["task_name"],
                "label": st["label"],
                "last_run_at": st["last_run_at"],
                "next_expected_at": st["next_expected_at"],
                "lateness_seconds": st["lateness_seconds"],
                "interval_seconds": st["interval_seconds"],
                "kind": "scheduled_beat_task",
            },
            "suggested_actions": [
                {
                    "action": "investigate_beat",
                    "label": "Check Celery Beat / worker — task not dispatching",
                },
            ],
        })

    return anomalies


# =========================================================================
# TELEMETRY SECTION — for the Ops Wall payload
# =========================================================================


def get_scheduled_tasks_telemetry(now=None):
    """
    Build the ``scheduled_tasks`` Ops Wall section.

    Returns a dict with a summary + per-task rows so an operator can see the
    freshness of every scheduled job, not just fire on a miss.
    """
    now = now or timezone.now()
    states = compute_scheduled_task_states(now)

    counts = {"OK": 0, "LATE": 0, "MISSED": 0, "NEVER_RUN": 0, "ERROR": 0}
    for st in states:
        counts[st["status"]] = counts.get(st["status"], 0) + 1
        # A task that ran but whose last run errored is surfaced separately.
        if st["status"] in ("OK", "LATE") and st["last_status"] == "error":
            counts["ERROR"] += 1

    if counts["MISSED"] > 0:
        overall = "MISSED"
    elif counts["ERROR"] > 0 or counts["LATE"] > 0:
        overall = "DEGRADED"
    else:
        overall = "OK"

    return {
        "status": overall,
        "total": len(states),
        "counts": counts,
        "tasks": states,
        "computed_at": now.isoformat(),
    }
