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
