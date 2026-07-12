"""
Confirmation Queue & Audit Pipeline Health — OPS-8a (Operational Hardening).

Two correctness-adjacent pipelines whose silent failure directly breaks trust:

* **Confirmation queue** — a user asks the Chief of Staff to do something that needs
  confirmation; if that pending confirmation silently stalls (the cache expires, the
  user never answers, nothing cleans it up), the **requested action never executes**
  and no one notices. `PendingAction` (`core_pendingaction`) is the durable truth:
  status lifecycle (pending/confirmed/cancelled/expired/edited), `created_at`,
  `expires_at`, `resolved_at`.
* **Audit pipeline** — the Constitution guarantees every action/decision is audited.
  We surface the audit *streams'* liveness so a flatline is visible.

Evidence-driven scope refinement (verified 2026-07-12)
------------------------------------------------------
Auditing is **synchronous / inline**: `record_decision` → `DecisionRecord.objects.create`
and `AIActionMetric.objects.create` are written at the moment of the event. There is
**no audit queue, no deferred writer, no "unapplied audits."** So the originally-scoped
"audit lag / oldest unapplied audit / delayed writes / failed processing" describe a
pipeline that does not exist — measuring them would fabricate a signal. The honest,
deterministic audit-health truth available is **stream liveness**: throughput
(writes/hour) + recency (age of the last write) for each audit stream. Facts, not a
verdict (Constitution I.4) — a quiet period legitimately has few audit writes, so audit
status stays informational; the operator/model interprets a flatline.

Architecture (matches OPS-2 / OPS-5 / api_health)
-------------------------------------------------
* All queries run ONLY in the SAME background cycle via
  `build_ops_stream_payload → _get_confirmation_audit_telemetry → this module`. The
  HTTP request path only reads the cached payload. Cache-guarded (`_TELEMETRY_TTL`).
* Deterministic aggregate reads (counts + min/max timestamps over indexed columns);
  each block is wrapped and degrades to `UNAVAILABLE` — never raises.
* **Telemetry-only** — no `OpsAnomaly`, no recovery, no remediation. Exposes existing
  truth (reuses `PendingAction` / `DecisionRecord` / `AIActionMetric`); introduces no
  new persistence and no new infrastructure.

Project: Whole Life Journey
Path: apps/core/ai_observability/confirmation_audit_monitor.py
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.core.ai_observability.storage_monitor import _overall_status

logger = logging.getLogger(__name__)

_TELEMETRY_CACHE_KEY = "wlj:ops:confirmation_audit"
_TELEMETRY_TTL = 300  # 5 min

# Confirmation thresholds.
STALLED_WARN = 1        # any orphaned pending (expired but never resolved) → look
STALLED_CRIT = 5
OLDEST_PENDING_WARN_S = 900   # a live pending older than 15m is unusual (cache TTL 300s)


def _confirmation_health(now):
    """Confirmation-queue health from the durable `PendingAction` record."""
    try:
        from apps.core.ai_governance.models import PendingAction

        pending = PendingAction.objects.filter(status=PendingAction.STATUS_PENDING)
        active_qs = pending.filter(expires_at__gte=now)
        active = active_qs.count()
        # Orphaned: still 'pending' but past expiry — the confirmation silently died
        # (cache evicted, user never answered, nothing marked it expired/resolved).
        stalled = pending.filter(expires_at__lt=now).count()

        oldest_age_s = None
        first = active_qs.order_by("created_at").values_list("created_at", flat=True).first()
        if first:
            oldest_age_s = int((now - first).total_seconds())

        # Age distribution of live pending confirmations.
        b5 = active_qs.filter(created_at__gte=now - timedelta(minutes=5)).count()
        b30 = active_qs.filter(
            created_at__lt=now - timedelta(minutes=5),
            created_at__gte=now - timedelta(minutes=30),
        ).count()
        bold = active_qs.filter(created_at__lt=now - timedelta(minutes=30)).count()

        # 24h flow (throughput / resolution health).
        since = now - timedelta(hours=24)
        created_24h = PendingAction.objects.filter(created_at__gte=since).count()
        resolved = PendingAction.objects.filter(resolved_at__gte=since)
        confirmed_24h = resolved.filter(status=PendingAction.STATUS_CONFIRMED).count()
        cancelled_24h = resolved.filter(status=PendingAction.STATUS_CANCELLED).count()

        if stalled >= STALLED_CRIT:
            status = "CRITICAL"
        elif stalled >= STALLED_WARN or (oldest_age_s or 0) > OLDEST_PENDING_WARN_S:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status": status,
            "pending_active": active,
            "stalled": stalled,
            "oldest_pending_age_s": oldest_age_s,
            "age_buckets": {"lt_5m": b5, "5_30m": b30, "gt_30m": bold},
            "flow_24h": {
                "created": created_24h,
                "confirmed": confirmed_24h,
                "cancelled": cancelled_24h,
            },
        }
    except Exception as e:
        logger.debug("OPS-8a confirmation probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def _stream_liveness(model, now):
    """(count_1h, last_write_age_s|None) for an audit stream — deterministic facts."""
    since = now - timedelta(hours=1)
    count_1h = model.objects.filter(created_at__gte=since).count()
    last = model.objects.order_by("-created_at").values_list("created_at", flat=True).first()
    age_s = int((now - last).total_seconds()) if last else None
    return count_1h, age_s


def _audit_health(now):
    """Audit-stream liveness (facts-only; synchronous audit has no queue/lag)."""
    try:
        from apps.core.ai_observability.models import AIActionMetric, DecisionRecord

        d_count, d_age = _stream_liveness(DecisionRecord, now)
        a_count, a_age = _stream_liveness(AIActionMetric, now)
        # Facts, not a verdict: a quiet period legitimately has no recent writes, so
        # this block stays HEALTHY. The operator/model reads a flatline from the facts.
        return {
            "status": "HEALTHY",
            "note": "synchronous audit — throughput/recency facts, no queue-lag exists",
            "decision_records": {"count_1h": d_count, "last_write_age_s": d_age},
            "action_metrics": {"count_1h": a_count, "last_write_age_s": a_age},
        }
    except Exception as e:
        logger.debug("OPS-8a audit probe failed: %s", e)
        return {"status": "UNAVAILABLE", "reason": str(e)[:200]}


def get_confirmation_audit_telemetry(now=None):
    """Build the ``confirmation_audit`` Ops Wall section (OPS-8a)."""
    cached = cache.get(_TELEMETRY_CACHE_KEY)
    if cached is not None:
        return cached

    now = now or timezone.now()
    confirmation = _confirmation_health(now)
    audit = _audit_health(now)

    result = {
        "status": _overall_status([confirmation, audit]),
        "confirmation": confirmation,
        "audit": audit,
        "measured_at": now.isoformat(),
    }
    cache.set(_TELEMETRY_CACHE_KEY, result, timeout=_TELEMETRY_TTL)
    return result
