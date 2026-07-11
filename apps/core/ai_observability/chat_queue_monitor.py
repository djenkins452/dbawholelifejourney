"""
Chat Queue Monitor — OPS-3.

Observability for the interactive chat-generation pipeline. Chat turns run as
Celery tasks (``run_chat_generation`` / ``run_chatgpt_cos_generation``, routed
to the ``CHAT_GENERATION_QUEUE``). When that queue backs up, stalls, or its
worker dies, the *product* — a user waiting on a reply — degrades, but nothing
on the Ops Wall showed it. OPS-3 makes chat backlog, stalls, and worker
starvation visible without reading logs.

How it works — passive lifecycle capture via Celery signals
-----------------------------------------------------------
No edits to the chat dispatch sites or the task bodies. Three Celery signals
(filtered to the chat task names) maintain a small set of cross-process Redis
structures:

* ``before_task_publish`` (fires in the web process at enqueue) → add the task
  to a **pending** sorted set scored by enqueue time.
* ``task_prerun`` (fires in the worker when it picks the task up) → move it to
  an **active** sorted set scored by start time, and record the queue-wait.
* ``task_postrun`` (fires in the worker on completion) → drop it from active
  and record throughput + duration.

From these the reader derives, deterministically:
* **queue depth** — pending (enqueued, not yet started)
* **oldest queued age** — now − oldest pending enqueue time
* **throughput** — completions in the trailing minute
* **queue wait** — avg time a turn waited before a worker started it
* **stuck detection** — a task active longer than the task time-limit
* **worker starvation** — pending work but nothing active and no recent
  completion (the worker that drains the chat queue is gone)

Everything is in Redis (cross-process; the web process publishes, the worker
consumes). Without Redis (dev in-memory broker) the recorders no-op and the
reader returns UNAVAILABLE — clear degradation, never a fabricated zero.

Project: Whole Life Journey
Path: apps/core/ai_observability/chat_queue_monitor.py
"""

import logging
import time

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Chat-generation task names (interactive turns). Both share CHAT_GENERATION_QUEUE.
_CHAT_TASK_NAMES = frozenset({
    "apps.ai.tasks.run_chat_generation",
    "apps.ai.chatgpt_cos.run_chatgpt_cos_generation",
})

_PREFIX = "wlj:ops:chat"
_PENDING_ZSET = f"{_PREFIX}:pending"      # member=task_id, score=enqueue epoch
_ACTIVE_ZSET = f"{_PREFIX}:active"        # member=task_id, score=start epoch
_WAITS_LIST = f"{_PREFIX}:waits"          # recent queue-wait ms
_COMPLETIONS_LIST = f"{_PREFIX}:completions"  # "epoch:dur_ms:1|0"

_LIST_CAP = 200                            # bounded rolling history
_STRUCT_TTL = 60 * 60                       # self-heal: structures expire in 1h

# Thresholds
WARN_DEPTH = 5
CRITICAL_DEPTH = 15
WARN_OLDEST_AGE_S = 30
CRITICAL_OLDEST_AGE_S = 90
STARVATION_WINDOW_S = 120     # pending but no start/completion for this long ⇒ starved
THROUGHPUT_WINDOW_S = 60      # completions counted as "per minute"

# A chat task past this (task time_limit is 120s) that is still "active" is stuck.
STUCK_ACTIVE_S = 130


def _redis():
    """
    Raw Redis client for the broker/cache, or None if not available.

    Uses the same connection approach as ``celery_health`` — short timeouts so a
    degraded Redis can never block the caller. Returns None for the dev
    in-memory broker so callers degrade gracefully.
    """
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
        logger.debug("OPS-3 redis client unavailable: %s", e)
        return None


# =========================================================================
# RECORDERS — driven by Celery signals (never raise)
# =========================================================================


def record_enqueued(task_id, now_epoch=None):
    """Add a chat turn to the pending set at enqueue time (web process)."""
    if not task_id:
        return
    try:
        client = _redis()
        if client is None:
            return
        score = now_epoch if now_epoch is not None else time.time()
        client.zadd(_PENDING_ZSET, {str(task_id): score})
        client.expire(_PENDING_ZSET, _STRUCT_TTL)
    except Exception as e:
        logger.debug("OPS-3 record_enqueued failed: %s", e)


def record_started(task_id, now_epoch=None):
    """Move a chat turn from pending to active and record its queue-wait."""
    if not task_id:
        return
    try:
        client = _redis()
        if client is None:
            return
        now_epoch = now_epoch if now_epoch is not None else time.time()
        tid = str(task_id)
        enqueued = client.zscore(_PENDING_ZSET, tid)
        client.zrem(_PENDING_ZSET, tid)
        if enqueued is not None:
            wait_ms = max(0, int((now_epoch - enqueued) * 1000))
            client.lpush(_WAITS_LIST, wait_ms)
            client.ltrim(_WAITS_LIST, 0, _LIST_CAP - 1)
            client.expire(_WAITS_LIST, _STRUCT_TTL)
        client.zadd(_ACTIVE_ZSET, {tid: now_epoch})
        client.expire(_ACTIVE_ZSET, _STRUCT_TTL)
    except Exception as e:
        logger.debug("OPS-3 record_started failed: %s", e)


def record_completed(task_id, success=True, now_epoch=None):
    """Drop a chat turn from active and record throughput + duration."""
    if not task_id:
        return
    try:
        client = _redis()
        if client is None:
            return
        now_epoch = now_epoch if now_epoch is not None else time.time()
        tid = str(task_id)
        started = client.zscore(_ACTIVE_ZSET, tid)
        client.zrem(_ACTIVE_ZSET, tid)
        dur_ms = max(0, int((now_epoch - started) * 1000)) if started else 0
        client.lpush(_COMPLETIONS_LIST, f"{now_epoch:.3f}:{dur_ms}:{1 if success else 0}")
        client.ltrim(_COMPLETIONS_LIST, 0, _LIST_CAP - 1)
        client.expire(_COMPLETIONS_LIST, _STRUCT_TTL)
    except Exception as e:
        logger.debug("OPS-3 record_completed failed: %s", e)


# =========================================================================
# CELERY SIGNAL HANDLERS
# =========================================================================


def _on_publish(sender=None, headers=None, **kwargs):
    """before_task_publish — chat task enqueued (protocol v2: id in headers)."""
    try:
        if sender not in _CHAT_TASK_NAMES:
            return
        task_id = (headers or {}).get("id")
        record_enqueued(task_id)
    except Exception:
        pass


def _on_prerun(task_id=None, task=None, sender=None, **kwargs):
    try:
        name = getattr(sender, "name", None) or getattr(task, "name", None)
        if name not in _CHAT_TASK_NAMES:
            return
        record_started(task_id)
    except Exception:
        pass


def _on_postrun(task_id=None, task=None, sender=None, state=None, **kwargs):
    try:
        name = getattr(sender, "name", None) or getattr(task, "name", None)
        if name not in _CHAT_TASK_NAMES:
            return
        record_completed(task_id, success=(state == "SUCCESS"))
    except Exception:
        pass


_SIGNALS_CONNECTED = False


def connect_signals():
    """Connect chat-queue Celery signals. Idempotent (AppConfig.ready)."""
    global _SIGNALS_CONNECTED
    if _SIGNALS_CONNECTED:
        return
    try:
        from celery.signals import (
            before_task_publish,
            task_postrun,
            task_prerun,
        )
        before_task_publish.connect(_on_publish, dispatch_uid="wlj_chat_publish")
        task_prerun.connect(_on_prerun, dispatch_uid="wlj_chat_prerun")
        task_postrun.connect(_on_postrun, dispatch_uid="wlj_chat_postrun")
        _SIGNALS_CONNECTED = True
        logger.info("Chat-queue monitor: Celery signals connected (OPS-3).")
    except Exception as e:
        logger.warning("Chat-queue monitor: signal connect failed: %s", e)


# =========================================================================
# READER — telemetry section (pure Redis reads)
# =========================================================================


def _recent_completions(client, now_epoch):
    """Parse the completions list into (epoch, dur_ms, success) tuples."""
    out = []
    try:
        for raw in client.lrange(_COMPLETIONS_LIST, 0, _LIST_CAP - 1):
            try:
                s = raw.decode() if isinstance(raw, bytes) else str(raw)
                epoch_s, dur_s, ok_s = s.split(":")
                out.append((float(epoch_s), int(dur_s), ok_s == "1"))
            except Exception:
                continue
    except Exception:
        pass
    return out


def get_chat_queue_telemetry(now=None):
    """
    Build the ``chat_queue`` Ops Wall section from the Redis structures.

    Pure reads (ZCARD/ZRANGE/LRANGE) — O(small). Returns a dict:
        status, queue_depth, oldest_age_s, active_count, stuck_count,
        throughput_per_min, avg_wait_ms, worker_starved, completed_recent,
        error_recent, measured_at. UNAVAILABLE when Redis is not reachable.
    """
    now = now or timezone.now()
    return get_chat_queue_telemetry_at(now.timestamp(), measured_at=now.isoformat())


def get_chat_queue_telemetry_at(now_epoch, measured_at=None):
    """
    Compute chat-queue health at an explicit epoch (seconds).

    Split out from ``get_chat_queue_telemetry`` so the derivation is
    deterministically testable without mocking wall-clock time.
    """
    measured_at = measured_at or timezone.now().isoformat()

    client = _redis()
    if client is None:
        return {
            "status": "UNAVAILABLE",
            "reason": "no Redis broker (dev in-memory) — chat queue not measurable",
            "queue_depth": None,
            "measured_at": measured_at,
        }

    try:
        # Pending (enqueued, not started)
        queue_depth = int(client.zcard(_PENDING_ZSET) or 0)
        oldest_age_s = None
        oldest = client.zrange(_PENDING_ZSET, 0, 0, withscores=True)
        if oldest:
            _member, score = oldest[0]
            oldest_age_s = max(0, int(now_epoch - score))

        # Active (started, not completed) + stuck detection
        active = client.zrange(_ACTIVE_ZSET, 0, -1, withscores=True)
        active_count = len(active)
        stuck_count = sum(
            1 for _m, score in active if (now_epoch - score) > STUCK_ACTIVE_S
        )

        # Throughput + error rate over the trailing window
        completions = _recent_completions(client, now_epoch)
        recent = [c for c in completions if (now_epoch - c[0]) <= THROUGHPUT_WINDOW_S]
        throughput_per_min = len(recent)
        error_recent = sum(1 for c in recent if not c[2])
        last_completion_age_s = None
        if completions:
            last_completion_age_s = int(now_epoch - max(c[0] for c in completions))

        # Queue wait (avg of recent samples)
        waits = []
        for raw in client.lrange(_WAITS_LIST, 0, _LIST_CAP - 1):
            try:
                waits.append(int(raw.decode() if isinstance(raw, bytes) else raw))
            except Exception:
                continue
        avg_wait_ms = round(sum(waits) / len(waits)) if waits else None

        # Worker starvation: work is waiting, nothing is running, and no worker
        # has completed anything recently ⇒ the chat-queue worker is gone.
        worker_starved = (
            queue_depth > 0
            and active_count == 0
            and (last_completion_age_s is None or last_completion_age_s > STARVATION_WINDOW_S)
            and (oldest_age_s is not None and oldest_age_s > STARVATION_WINDOW_S)
        )

        # --- Status roll-up ---
        if stuck_count > 0 or worker_starved:
            status = "CRITICAL"
        elif queue_depth >= CRITICAL_DEPTH or (
            oldest_age_s is not None and oldest_age_s >= CRITICAL_OLDEST_AGE_S
        ):
            status = "CRITICAL"
        elif queue_depth >= WARN_DEPTH or (
            oldest_age_s is not None and oldest_age_s >= WARN_OLDEST_AGE_S
        ):
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "queue_depth": queue_depth,
            "oldest_age_s": oldest_age_s,
            "active_count": active_count,
            "stuck_count": stuck_count,
            "throughput_per_min": throughput_per_min,
            "avg_wait_ms": avg_wait_ms,
            "worker_starved": worker_starved,
            "completed_recent": throughput_per_min,
            "error_recent": error_recent,
            "last_completion_age_s": last_completion_age_s,
            "measured_at": measured_at,
        }
    except Exception as e:
        logger.debug("OPS-3 chat queue telemetry failed: %s", e)
        return {
            "status": "UNAVAILABLE",
            "reason": str(e)[:200],
            "queue_depth": None,
            "measured_at": measured_at,
        }
