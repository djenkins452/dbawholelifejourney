"""
OpenAI Upstream Health Monitor — OPS-4.

External-model availability observability for the Ops Wall. When the
conversational model provider (currently OpenAI) is slow or failing, WLJ itself
is healthy but the *product* is degraded — and until now the wall could not
distinguish "WLJ is broken" from "the upstream model is down". OPS-4 makes that
attribution immediate.

How it works — passive, zero added request-path work
----------------------------------------------------
Every LLM call already flows through ``AIService._log_usage`` (success and
failure, streaming and non-streaming). OPS-4 hooks a single fire-and-forget
recorder there: ``record_llm_outcome(success, latency_ms, ...)``. No synthetic
health-check pings are made (they cost money and add an external dependency to
the ops cycle); availability is inferred from the traffic that is already
happening. The recorder does a handful of atomic Redis counter bumps and
returns — it never raises and adds no measurable latency to a call that already
took seconds.

State is kept entirely in the cache (Redis in prod), cross-process safe via
atomic ``incr``:
* per-minute OK / error / latency buckets  → windowed availability + latency
* ``last_success`` / ``last_failure`` timestamps
* ``consecutive_failures`` counter (incr on failure, delete on success)

The reader also consults the existing ``openai_rate_limited`` circuit-breaker
flag set by ``apps/ai/services.py`` so a tripped breaker shows as DEGRADED.

Degradation states
------------------
* **OUTAGE**   — several consecutive failures / no success for a while: upstream
  is down. This is the state that says "OpenAI, not WLJ".
* **DEGRADED** — elevated error rate in the window, or the rate-limit breaker is
  active.
* **HEALTHY**  — recent successes, low error rate.
* **IDLE**     — no calls in the window (nothing to judge).

Project: Whole Life Journey
Path: apps/core/ai_observability/upstream_health.py
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

_PREFIX = "wlj:ops:upstream"
_LAST_SUCCESS = f"{_PREFIX}:last_success"
_LAST_FAILURE = f"{_PREFIX}:last_failure"
_LAST_ERROR_MSG = f"{_PREFIX}:last_error"
_CONSECUTIVE = f"{_PREFIX}:consecutive_failures"

_BUCKET_TTL = 60 * 45          # keep per-minute buckets 45 min
_WINDOW_MINUTES = 30           # availability/latency window
_STATE_TTL = 60 * 60 * 24      # last_success/failure persist a day

# Thresholds
CONSECUTIVE_OUTAGE = 3         # N straight failures ⇒ OUTAGE
ERROR_RATE_DEGRADED = 0.25     # >25% window error rate ⇒ DEGRADED
OUTAGE_SILENCE_MINUTES = 10    # no success + recent failures for this long ⇒ OUTAGE


def _minute_key(kind, epoch_minute):
    return f"{_PREFIX}:{kind}:{epoch_minute}"


def _bump(key, amount, ttl):
    """
    Atomic-ish counter increment that tolerates a missing key.

    django-redis ``incr`` raises if the key is absent, so on the first write of
    a bucket we fall back to ``set``. A rare race between two processes doing
    the initial ``set`` loses at most one increment — acceptable for
    observability counters.
    """
    try:
        cache.incr(key, amount)
    except Exception:
        try:
            cache.set(key, amount, timeout=ttl)
        except Exception as e:
            logger.debug("OPS-4 bucket bump failed for %s: %s", key, e)


def _now_epoch_minute(now=None):
    now = now or timezone.now()
    return int(now.timestamp() // 60)


# =========================================================================
# RECORDER — called passively from AIService._log_usage (both paths)
# =========================================================================


def record_llm_outcome(success, latency_ms=0, error_class=None,
                       status_code=None, now=None):
    """
    Record one upstream model call outcome. Fire-and-forget; never raises.

    Args:
        success: bool — did the call return a usable response.
        latency_ms: int — round-trip latency in ms (0 if unknown).
        error_class: optional exception class name for the last-error label.
        status_code: optional HTTP status for the last-error label.
    """
    try:
        now = now or timezone.now()
        minute = _now_epoch_minute(now)
        latency_ms = int(latency_ms or 0)

        if success:
            _bump(_minute_key("ok", minute), 1, _BUCKET_TTL)
            if latency_ms > 0:
                _bump(_minute_key("lat_sum", minute), latency_ms, _BUCKET_TTL)
                _bump(_minute_key("lat_cnt", minute), 1, _BUCKET_TTL)
            cache.set(_LAST_SUCCESS, now.isoformat(), timeout=_STATE_TTL)
            try:
                cache.delete(_CONSECUTIVE)
            except Exception:
                pass
        else:
            _bump(_minute_key("err", minute), 1, _BUCKET_TTL)
            cache.set(_LAST_FAILURE, now.isoformat(), timeout=_STATE_TTL)
            label = "/".join(
                str(p) for p in (error_class, status_code) if p not in (None, "")
            ) or "error"
            cache.set(_LAST_ERROR_MSG, label[:200], timeout=_STATE_TTL)
            _bump(_CONSECUTIVE, 1, _STATE_TTL)
    except Exception as e:  # telemetry must NEVER break an LLM call
        logger.debug("OPS-4 record_llm_outcome failed: %s", e)


# =========================================================================
# READER — telemetry section (safe to call anywhere: pure cache reads)
# =========================================================================


def _window_counts(now):
    """Sum OK/error/latency buckets across the trailing window."""
    base_minute = _now_epoch_minute(now)
    ok = err = lat_sum = lat_cnt = 0
    for i in range(_WINDOW_MINUTES):
        m = base_minute - i
        ok += int(cache.get(_minute_key("ok", m)) or 0)
        err += int(cache.get(_minute_key("err", m)) or 0)
        lat_sum += int(cache.get(_minute_key("lat_sum", m)) or 0)
        lat_cnt += int(cache.get(_minute_key("lat_cnt", m)) or 0)
    return ok, err, lat_sum, lat_cnt


def _parse_iso(value):
    if not value:
        return None
    try:
        from django.utils.dateparse import parse_datetime
        return parse_datetime(value)
    except Exception:
        return None


def get_upstream_health_telemetry(now=None):
    """
    Build the ``upstream_health`` Ops Wall section from cached counters.

    Pure cache reads — no external calls, no DB, safe on any path. Returns:
        status, availability_pct, avg_latency_ms, total_calls, error_count,
        consecutive_failures, breaker_active, last_success_at,
        last_failure_at, last_error, window_minutes, minutes_since_success.
    """
    now = now or timezone.now()

    ok, err, lat_sum, lat_cnt = _window_counts(now)
    total = ok + err
    error_rate = (err / total) if total else 0.0
    avg_latency = round(lat_sum / lat_cnt) if lat_cnt else None
    availability = round(ok / total * 100, 1) if total else None

    try:
        consecutive = int(cache.get(_CONSECUTIVE) or 0)
    except Exception:
        consecutive = 0
    breaker_active = bool(cache.get("openai_rate_limited"))

    last_success_raw = cache.get(_LAST_SUCCESS)
    last_failure_raw = cache.get(_LAST_FAILURE)
    last_success_dt = _parse_iso(last_success_raw)
    minutes_since_success = None
    if last_success_dt:
        minutes_since_success = int((now - last_success_dt).total_seconds() // 60)

    # --- Degradation state machine ---
    recent_failure = False
    last_failure_dt = _parse_iso(last_failure_raw)
    if last_failure_dt:
        recent_failure = (now - last_failure_dt) <= timedelta(minutes=OUTAGE_SILENCE_MINUTES)

    silent_outage = (
        recent_failure
        and minutes_since_success is not None
        and minutes_since_success >= OUTAGE_SILENCE_MINUTES
    )

    if total == 0 and consecutive == 0 and not breaker_active:
        status = "IDLE"
    elif consecutive >= CONSECUTIVE_OUTAGE or silent_outage:
        status = "OUTAGE"
    elif breaker_active or (total > 0 and error_rate >= ERROR_RATE_DEGRADED):
        status = "DEGRADED"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "availability_pct": availability,
        "avg_latency_ms": avg_latency,
        "total_calls": total,
        "ok_count": ok,
        "error_count": err,
        "error_rate_pct": round(error_rate * 100, 1) if total else 0.0,
        "consecutive_failures": consecutive,
        "breaker_active": breaker_active,
        "last_success_at": last_success_raw,
        "last_failure_at": last_failure_raw,
        "last_error": cache.get(_LAST_ERROR_MSG),
        "minutes_since_success": minutes_since_success,
        "window_minutes": _WINDOW_MINUTES,
        "computed_at": now.isoformat(),
    }
