"""
Background Task Health Monitor — OPS-7.

The Ops Wall already sees *specific* slices of background work: workers
(`celery_health`), the chat queue (`chat_queue`, OPS-3), Beat schedules
(`scheduled_tasks`, OPS-1), and per-engine runs (`EngineRun` + ERROR_SPIKE). What
it CANNOT see today is the **pool-wide task lifecycle**: which tasks — of ANY
name — are currently stuck, failing, retrying, or being revoked.

Why this is genuinely uncovered (investigated 2026-07-11)
---------------------------------------------------------
* `CELERY_TASK_IGNORE_RESULT = True` and there is no `django_celery_results`
  backend, so Celery persists **no** per-task SUCCESS/FAILURE/RETRY history to
  query. The only durable history is engine-scoped (`EngineRun`), Beat-scoped
  (`ScheduledTaskRun`, current-state only), or chat-scoped (OPS-3 Redis).
* The Celery `task_failure`, `task_retry`, and `task_revoked` signals are
  connected NOWHERE. Retries and general (non-engine) failures are invisible.

What this does (mirrors OPS-3's proven passive-capture pattern)
---------------------------------------------------------------
Connects the WORKER-SIDE Celery signals for **all** tasks and records them into
self-expiring Redis structures (no model, no migration):
* `task_prerun` / `task_postrun` → a live "active" set → oldest-active age +
  stuck detection (active past the task time-limit) across the whole pool.
* `task_failure` / `task_retry` / `task_revoked` → bounded rolling lists →
  failure volume + recurring-vs-isolated (by task name), retry patterns, revokes.

Boundaries
----------
* **Worker-side only.** Every signal used here fires in the worker
  (`task_prerun/postrun/failure/retry/revoked`) — NOT `before_task_publish`. So
  there is ZERO request-path work (request-path safety preserved). The reader
  runs only in the SAME background cycle and reads Redis.
* **Telemetry-only** — like OPS-2/3/4/5, no `OpsAnomaly`, no recovery, no
  autonomous remediation. It exposes existing lifecycle truth; it does not act.
* **Complements, does not duplicate:** `celery_health` = worker/queue view;
  `chat_queue` = chat-specific depth/wait/throughput; this = pool-wide
  failure/retry/stuck across every task name.
* Recorders NEVER raise into task execution; no Redis (dev) → they no-op and the
  reader returns UNAVAILABLE.

Project: Whole Life Journey
Path: apps/core/ai_observability/task_health_monitor.py
"""

import logging
import time

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_PREFIX = "wlj:ops:taskwork"
_ACTIVE_ZSET = f"{_PREFIX}:active"          # member=task_id, score=start epoch
_ACTIVE_NAMES = f"{_PREFIX}:active_names"   # hash task_id -> task name
_FAILURES_LIST = f"{_PREFIX}:failures"      # "epoch:taskname"
_RETRIES_LIST = f"{_PREFIX}:retries"        # "epoch:taskname"
_REVOKED_LIST = f"{_PREFIX}:revoked"        # "epoch:taskname"

_LIST_CAP = 200
_STRUCT_TTL = 60 * 60  # self-heal: structures expire in 1h

# A task active past the hard time-limit (CELERY_TASK_TIME_LIMIT=120) is stuck.
STUCK_ACTIVE_S = 130
# Failure-volume thresholds over the rolling window (~1h / last 200).
FAILURE_WARN = 5
FAILURE_CRIT = 20
# Same task name failing/retrying this many times ⇒ "recurring" (systemic).
RECURRING_THRESHOLD = 3


def _redis():
    """Broker/cache Redis client with short timeouts, or None (dev/degraded)."""
    url = (
        getattr(settings, "CELERY_BROKER_URL", None)
        or getattr(settings, "REDIS_URL", None)
    )
    if not url or str(url).startswith("memory://"):
        return None
    try:
        import redis
        return redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    except Exception as e:
        logger.debug("OPS-7 redis client unavailable: %s", e)
        return None


# =========================================================================
# RECORDERS — driven by Celery worker signals (never raise)
# =========================================================================


def record_started(task_id, name, now_epoch=None):
    if not task_id:
        return
    try:
        client = _redis()
        if client is None:
            return
        tid = str(task_id)
        score = now_epoch if now_epoch is not None else time.time()
        client.zadd(_ACTIVE_ZSET, {tid: score})
        client.expire(_ACTIVE_ZSET, _STRUCT_TTL)
        if name:
            client.hset(_ACTIVE_NAMES, tid, name)
            client.expire(_ACTIVE_NAMES, _STRUCT_TTL)
    except Exception as e:
        logger.debug("OPS-7 record_started failed: %s", e)


def record_finished(task_id):
    """Drop a task from the active set (postrun / failure / revoked)."""
    if not task_id:
        return
    try:
        client = _redis()
        if client is None:
            return
        tid = str(task_id)
        client.zrem(_ACTIVE_ZSET, tid)
        client.hdel(_ACTIVE_NAMES, tid)
    except Exception as e:
        logger.debug("OPS-7 record_finished failed: %s", e)


def _record_event(list_key, name, now_epoch=None):
    try:
        client = _redis()
        if client is None:
            return
        epoch = now_epoch if now_epoch is not None else time.time()
        client.lpush(list_key, f"{epoch:.3f}:{name or 'unknown'}")
        client.ltrim(list_key, 0, _LIST_CAP - 1)
        client.expire(list_key, _STRUCT_TTL)
    except Exception as e:
        logger.debug("OPS-7 record event failed (%s): %s", list_key, e)


def record_failure(name, now_epoch=None):
    _record_event(_FAILURES_LIST, name, now_epoch)


def record_retry(name, now_epoch=None):
    _record_event(_RETRIES_LIST, name, now_epoch)


def record_revoked(name, now_epoch=None):
    _record_event(_REVOKED_LIST, name, now_epoch)


# =========================================================================
# READER — telemetry section (background cycle only)
# =========================================================================


def _decode(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


def _aggregate_by_name(entries):
    """['epoch:name', …] → (total, [{name, count} … top 5], recurring_bool)."""
    counts = {}
    for e in entries:
        e = _decode(e)
        _, _, name = e.partition(":")
        counts[name] = counts.get(name, 0) + 1
    top = sorted(
        ({"name": n, "count": c} for n, c in counts.items()),
        key=lambda x: x["count"], reverse=True,
    )[:5]
    recurring = any(c >= RECURRING_THRESHOLD for c in counts.values())
    return len(entries), top, recurring


def get_task_health_telemetry(now=None):
    """Build the ``task_health`` Ops Wall section (pool-wide task lifecycle)."""
    now = now or timezone.now()
    client = _redis()
    if client is None:
        return {
            "status": "UNAVAILABLE",
            "reason": "no Redis configured (dev in-memory broker)",
        }
    try:
        now_epoch = time.time()
        # Active / stuck.
        active_members = client.zrange(_ACTIVE_ZSET, 0, -1, withscores=True)
        active_count = len(active_members)
        oldest_age_s = None
        stuck = []
        if active_members:
            oldest_age_s = round(now_epoch - active_members[0][1])
            for tid, score in active_members:
                if now_epoch - score >= STUCK_ACTIVE_S:
                    name = _decode(client.hget(_ACTIVE_NAMES, tid)) or "unknown"
                    stuck.append({"task": name, "age_s": round(now_epoch - score)})
        stuck = sorted(stuck, key=lambda s: s["age_s"], reverse=True)[:5]

        fail_total, fail_top, fail_recurring = _aggregate_by_name(
            client.lrange(_FAILURES_LIST, 0, -1)
        )
        retry_total, retry_top, _ = _aggregate_by_name(
            client.lrange(_RETRIES_LIST, 0, -1)
        )
        revoked_total, _, _ = _aggregate_by_name(client.lrange(_REVOKED_LIST, 0, -1))

        # Status roll-up.
        stuck_count = len(stuck)
        if stuck_count >= 3 or fail_total >= FAILURE_CRIT:
            status = "CRITICAL"
        elif stuck_count >= 1 or fail_total >= FAILURE_WARN or fail_recurring:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "active": {
                "count": active_count,
                "oldest_age_s": oldest_age_s,
                "stuck_count": stuck_count,
                "stuck_tasks": stuck,
            },
            "failures": {
                "recent_count": fail_total,
                "recurring": fail_recurring,
                "top_by_name": fail_top,
            },
            "retries": {"recent_count": retry_total, "top_by_name": retry_top},
            "revoked": {"recent_count": revoked_total},
            "window": "last ~1h / 200 events",
            "measured_at": now.isoformat(),
        }
    except Exception as e:
        logger.debug("OPS-7 task_health read failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


# =========================================================================
# SIGNAL WIRING — worker-side lifecycle for ALL tasks
# =========================================================================


def _task_name(sender=None, task=None, request=None):
    for obj in (sender, task):
        name = getattr(obj, "name", None)
        if name:
            return name
    if request is not None:
        return getattr(request, "task", None) or getattr(request, "name", None)
    return None


def _on_prerun(task_id=None, task=None, sender=None, **kwargs):
    try:
        record_started(task_id, _task_name(sender, task))
    except Exception:
        pass


def _on_postrun(task_id=None, task=None, sender=None, state=None, **kwargs):
    try:
        record_finished(task_id)
    except Exception:
        pass


def _on_failure(task_id=None, sender=None, **kwargs):
    try:
        record_failure(_task_name(sender))
        record_finished(task_id)
    except Exception:
        pass


def _on_retry(sender=None, request=None, **kwargs):
    try:
        record_retry(_task_name(sender, request=request))
    except Exception:
        pass


def _on_revoked(sender=None, request=None, **kwargs):
    try:
        name = _task_name(sender, request=request)
        record_revoked(name)
        record_finished(getattr(request, "id", None))
    except Exception:
        pass


_SIGNALS_CONNECTED = False


def connect_signals():
    """Connect worker-side task-lifecycle signals for all tasks. Idempotent."""
    global _SIGNALS_CONNECTED
    if _SIGNALS_CONNECTED:
        return
    try:
        from celery.signals import (
            task_failure,
            task_postrun,
            task_prerun,
            task_retry,
            task_revoked,
        )
        task_prerun.connect(_on_prerun, dispatch_uid="wlj_taskwork_prerun")
        task_postrun.connect(_on_postrun, dispatch_uid="wlj_taskwork_postrun")
        task_failure.connect(_on_failure, dispatch_uid="wlj_taskwork_failure")
        task_retry.connect(_on_retry, dispatch_uid="wlj_taskwork_retry")
        task_revoked.connect(_on_revoked, dispatch_uid="wlj_taskwork_revoked")
        _SIGNALS_CONNECTED = True
        logger.info("Task-health monitor: Celery signals connected (OPS-7).")
    except Exception as e:
        logger.warning("Task-health monitor: signal connect failed: %s", e)
