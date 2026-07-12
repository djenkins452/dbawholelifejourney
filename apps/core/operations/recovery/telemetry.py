"""
WLJ Operations — recovery telemetry publisher (Phase II, read-only).

Operations publishes its OWN truth to a cache key; the Ops Wall payload (built in
``ai_observability``) merely READS that key. This preserves the frozen import
boundary (§11): ``ai_observability`` never imports ``operations`` — it only reads a
cache value the recovery cycle wrote. The cache key literal is duplicated (not
imported) in ``ops_telemetry._get_recovery_telemetry`` with a pointer comment.

Everything here is deterministic facts (counts, recent audit rows) — never a verdict
(Constitution I.4).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache as django_cache
from django.utils import timezone

from apps.core.operations.models import RecoveryAttempt

logger = logging.getLogger(__name__)

# Written by the recovery cycle, read by ops_telemetry._get_recovery_telemetry.
OPS_RECOVERY_CACHE_KEY = "wlj:ops:recovery"
OPS_RECOVERY_CACHE_TTL = 180  # seconds

# Human-readable reason per incident type (facts, not verdicts). Fallback below.
_EVENT_REASONS = {
    "MISSED_RUN": "Scheduled task missed its expected cadence.",
    "ENGINE_STARVATION": "Engine produced no runs within its expected window.",
    "MATURITY_SNAPSHOT_STALE": "System maturity snapshot went stale.",
}


def _friendly_title(engine_name: str) -> str:
    """Humanise a task path / engine name for the event headline (facts only)."""
    if not engine_name:
        return "Recovery"
    leaf = engine_name.rsplit(".", 1)[-1]
    if leaf.endswith("_task"):
        leaf = leaf[:-5]
    words = leaf.replace("_", " ").strip()
    return words.title() if words else engine_name


def _duration_seconds(row):
    """Deterministic recovery duration = resolution time − attempt time.

    ``updated_at`` (auto_now) is set when the deferred attempt is RESOLVED, so for a
    verified/failed row this is the real elapsed time. None when not yet resolved or
    on historical rows written before ``updated_at`` existed.
    """
    if row.updated_at and row.created_at and row.updated_at > row.created_at:
        return round((row.updated_at - row.created_at).total_seconds())
    return None


def _max_attempts_for(anomaly_type):
    """Policy max_attempts for the incident's handler (config, not a query)."""
    try:
        from apps.core.operations.recovery.base import registry
        handler = registry.handler_for(anomaly_type)
        return getattr(handler.policy, "max_attempts", None) if handler else None
    except Exception:  # pragma: no cover - defensive; never break telemetry
        return None


def _build_recovery_events(window_start, now):
    """Compose prominent operator EVENTS from real (ACTIVE) recovery outcomes.

    A deterministic reduction over the RecoveryAttempt rows already written by the
    engine — never a new decision, never a verdict. Only REAL recoveries surface
    (``mode=ACTIVE``); shadow simulations are excluded by construction. Each event
    is self-contained (incident, action, verification, duration, retry history,
    escalation status, timestamps, id) so the UI needs no follow-up query.
    """
    from collections import defaultdict

    rows = list(
        RecoveryAttempt.objects.filter(
            created_at__gte=window_start, mode=RecoveryAttempt.MODE_ACTIVE
        ).order_by("-created_at")[:100]
    )
    by_incident = defaultdict(list)
    for r in rows:
        by_incident[(r.anomaly_type, r.engine_name)].append(r)

    events = []
    for r in rows:
        if r.phase == RecoveryAttempt.PHASE_ESCALATED:
            kind, headline, verification = "escalated", "Recovery Escalated", "Failed"
        elif r.outcome == RecoveryAttempt.OUTCOME_FAILED:
            kind, headline, verification = "failed", "Recovery Failed", "Failed"
        elif r.phase == RecoveryAttempt.PHASE_VERIFIED and r.outcome == RecoveryAttempt.OUTCOME_SUCCESS:
            kind, headline, verification = "success", "Recovery Successful", "Passed"
        else:
            continue  # pending / in-flight — not yet a completed event

        incident_rows = by_incident.get((r.anomaly_type, r.engine_name), [])
        attempts = [a for a in incident_rows if a.phase == RecoveryAttempt.PHASE_RECOVER_ATTEMPTED]
        escalated = any(a.phase == RecoveryAttempt.PHASE_ESCALATED for a in incident_rows)
        max_attempts = _max_attempts_for(r.anomaly_type)
        if kind == "failed" and not escalated and max_attempts and len(attempts) < max_attempts:
            next_retry = "Will retry next cycle (after cooldown)."
        elif kind == "failed":
            next_retry = "Retries exhausted."
        else:
            next_retry = None

        events.append({
            "id": r.id,
            "kind": kind,                       # success | failed | escalated
            "headline": headline,
            "title": _friendly_title(r.engine_name),
            "task": r.engine_name,
            "monitor_key": r.monitor_key,
            "anomaly_type": r.anomaly_type,
            "classification": r.classification,
            "reason": _EVENT_REASONS.get(r.anomaly_type, f"{r.anomaly_type} incident."),
            "action": r.action_taken,
            "verification": verification,       # Passed | Failed
            "duration_seconds": _duration_seconds(r),
            "attempt_number": r.attempt_number,
            "retry_count": len(attempts),
            "escalation_status": "Escalated to engineering" if escalated else "None",
            "next_retry": next_retry,
            "error": r.error or "",
            "attempted_at": r.created_at.isoformat(),
            "resolved_at": r.updated_at.isoformat() if r.updated_at else None,
            "time": r.created_at.isoformat(),
            "retries": [
                {
                    "time": a.created_at.isoformat(),
                    "phase": a.phase,
                    "outcome": a.outcome,
                    "attempt_number": a.attempt_number,
                    "action": a.action_taken,
                }
                for a in sorted(incident_rows, key=lambda a: a.created_at)
            ],
        })
        if len(events) >= 10:
            break
    return events


def build_recovery_telemetry(now=None) -> dict:
    """Assemble the read-only recovery section from the RecoveryAttempt audit rows.

    Exposes deterministic facts ONLY (counts, config, audit rows) — never a verdict
    (Constitution I.4). Includes a ``config`` block (mode source, handler roster,
    operator flags/allowlists) so the Ops Wall can render Recovery as a first-class
    operational component even when recovery is DISABLED (config is truth that
    exists regardless of whether the engine is allowed to act).
    """
    from apps.core.operations.recovery.handlers import recovery_config_snapshot
    from apps.core.operations.recovery.mode import (
        DISABLED,
        describe_mode_source,
        get_recovery_mode,
    )

    now = now or timezone.now()
    window_start = now - timedelta(hours=24)

    recent = list(
        RecoveryAttempt.objects.filter(created_at__gte=window_start).order_by("-created_at")[:25]
    )
    all_window = RecoveryAttempt.objects.filter(created_at__gte=window_start)

    verified_24h = all_window.filter(phase=RecoveryAttempt.PHASE_VERIFIED,
                                     outcome=RecoveryAttempt.OUTCOME_SUCCESS).count()
    recovered_24h = all_window.filter(phase=RecoveryAttempt.PHASE_RECOVER_ATTEMPTED).count()
    escalated_24h = all_window.filter(phase=RecoveryAttempt.PHASE_ESCALATED).count()
    failed_24h = all_window.filter(outcome=RecoveryAttempt.OUTCOME_FAILED).count()
    pending = RecoveryAttempt.objects.filter(outcome=RecoveryAttempt.OUTCOME_PENDING).count()
    # Shadow-mode simulated decisions (never executed) — kept in their OWN counters
    # so a simulated "would recover" can never be counted as a real recovery.
    shadowed_24h = all_window.filter(phase=RecoveryAttempt.PHASE_SHADOW).count()
    would_recover_24h = all_window.filter(
        phase=RecoveryAttempt.PHASE_SHADOW,
        evidence_before__would_execute=True,
    ).count()

    # Most recent recovery activity of ANY kind (not windowed) — the honest
    # "last activity" fact. No row exists when recovery has never acted (e.g.
    # DISABLED, or ACTIVE/SHADOW with no incidents) → None.
    latest = RecoveryAttempt.objects.order_by("-created_at").values_list(
        "created_at", flat=True
    ).first()

    mode = get_recovery_mode()
    section = {
        "mode": mode,                       # DISABLED | SHADOW | ACTIVE
        "mode_source": describe_mode_source(),
        "enabled": mode != DISABLED,        # back-compat for existing JS
        "status": "ATTENTION" if escalated_24h else "OK",
        "config": recovery_config_snapshot(),
        "last_activity": latest.isoformat() if latest else None,
        # Prominent operator events — real (ACTIVE) recoveries only; never shadow.
        "events": _build_recovery_events(window_start, now),
        "counts": {
            "recovered_24h": recovered_24h,
            "verified_24h": verified_24h,
            "escalated_24h": escalated_24h,
            "failed_24h": failed_24h,
            "pending": pending,
            "shadowed_24h": shadowed_24h,
            "would_recover_24h": would_recover_24h,
        },
        "recent": [
            {
                "time": r.created_at.isoformat(),
                "monitor_key": r.monitor_key,
                "anomaly_type": r.anomaly_type,
                "engine_name": r.engine_name,
                "classification": r.classification,
                "phase": r.phase,
                "outcome": r.outcome,
                "mode": r.mode,
                "simulated": r.mode == RecoveryAttempt.MODE_SHADOW,
                "action": r.action_taken,
            }
            for r in recent
        ],
        "computed_at": now.isoformat(),
    }
    return section


def publish_recovery_telemetry(now=None) -> dict:
    """Build and cache the recovery section for the Ops Wall to read."""
    section = build_recovery_telemetry(now)
    django_cache.set(OPS_RECOVERY_CACHE_KEY, section, timeout=OPS_RECOVERY_CACHE_TTL)
    return section
