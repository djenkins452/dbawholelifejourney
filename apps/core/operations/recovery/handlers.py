"""
WLJ Operations — pilot recovery handlers (Phase II first cut).

ONE fully-wired R1 pilot: re-enqueue a missed Beat task, restricted to an operator
allowlist of provably-idempotent recompute/cleanup tasks
(WLJ_OPERATIONS_PHASE2_PLAN.md §1.1 Pilot 2). Verification reuses the OPS-1 freshness
predicate (``compute_scheduled_task_states``) — the exact detector that raised the
MISSED_RUN incident.

Ships DARK and EMPTY: ``OPS_RECOVERY_ENABLED=False`` disables the whole cycle, and
``OPS_RECOVERY_BEAT_RETRY_ALLOWLIST`` is empty by default, so even when recovery is
enabled nothing runs until an operator adds a specific task name. A task not on the
allowlist stays R0 (observe-only).

Deferred (not in this cut): snapshot-refresh (its condition — a stale snapshot — is
already a downstream symptom of a missed Beat task, covered by THIS handler; a
separate handler would double-cover one condition, violating single-authority
III.1); chat-queue requeue (unprovable idempotency/dedup). See vision ADR-16.
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.core.operations.recovery.base import (
    RecoveryDiagnosis,
    RecoveryHandler,
    RecoveryOutcome,
    VerificationResult,
    registry,
)
from apps.core.operations.recovery.policy import R0, R1, RecoveryPolicy

logger = logging.getLogger(__name__)


def _beat_retry_allowlist() -> frozenset[str]:
    """Operator allowlist of idempotent recompute/cleanup task names (empty default)."""
    raw = getattr(settings, "OPS_RECOVERY_BEAT_RETRY_ALLOWLIST", ()) or ()
    return frozenset(str(x) for x in raw)


class BeatTaskRetryHandler(RecoveryHandler):
    """R1 — re-enqueue an allowlisted, idempotent Beat task that OPS-1 flagged MISSED."""

    monitor_key = "scheduled_task"
    handled_anomaly_types = frozenset({"MISSED_RUN"})
    policy = RecoveryPolicy(
        classification=R1,
        max_attempts=2,          # finite even for R1 — no unbounded loop
        cooldown_seconds=120,    # ≥ typical short cadence; anti-thrash
        recurrence_window_hours=24,
        recurrence_limit=5,      # keeps missing → permanent-fix escalation
    )

    def diagnose(self, anomaly) -> RecoveryDiagnosis:
        task_name = (anomaly.engine_name or "").strip()
        allow = task_name in _beat_retry_allowlist()
        enabled = bool(getattr(settings, "OPS_RECOVERY_BEAT_RETRY", False))
        recoverable = allow and enabled
        return RecoveryDiagnosis(
            target=task_name,
            reason=(
                f"Beat task '{task_name}' is MISSED (OPS-1)."
                + ("" if recoverable else " Not allowlisted/enabled → observe-only (R0).")
            ),
            evidence={
                "task_name": task_name,
                "allowlisted": allow,
                "handler_enabled": enabled,
            },
            recoverable=recoverable,
        )

    def recover(self, diagnosis: RecoveryDiagnosis) -> RecoveryOutcome:
        """Re-enqueue the task by name via the non-blocking safe path.

        Idempotent: the allowlist only contains recompute/cleanup tasks whose
        re-run overwrites/cleans again. The effect is asynchronous, so verification
        is DEFERRED to a later cycle (never closed optimistically).
        """
        from celery import current_app

        from apps.core.celery_utils import safe_enqueue

        task_name = diagnosis.target
        task_obj = current_app.tasks.get(task_name)
        if task_obj is None:
            # Registered as a Beat schedule but not importable here → cannot act.
            return RecoveryOutcome(
                action_taken=f"Task '{task_name}' not resolvable in this worker; no action.",
                verification_deferred=False,
                evidence={"enqueued": False, "reason": "task_not_registered"},
            )
        enqueued = safe_enqueue(task_obj)
        return RecoveryOutcome(
            action_taken=(
                f"Re-enqueued Beat task '{task_name}'"
                + ("" if enqueued else " (broker unavailable — enqueue failed)")
            ),
            verification_deferred=enqueued,  # if broker down, nothing to verify later
            evidence={"enqueued": enqueued},
        )

    def verify(self, diagnosis: RecoveryDiagnosis) -> VerificationResult:
        """Healthy iff the OPS-1 predicate no longer reports the task MISSED.

        Reuses the EXACT detector predicate (``compute_scheduled_task_states``) —
        "recovered" is provably the negation of "detected".
        """
        from apps.core.ai_observability.scheduled_task_monitor import (
            compute_scheduled_task_states,
        )

        task_name = diagnosis.target
        state = next(
            (s for s in compute_scheduled_task_states() if s["task_name"] == task_name),
            None,
        )
        status = state["status"] if state else "UNKNOWN"
        healthy = status in {"OK", "LATE"}  # not MISSED / NEVER_RUN / UNKNOWN
        return VerificationResult(
            healthy=healthy,
            evidence={"task_name": task_name, "status": status},
        )


def register_default_handlers() -> None:
    """Register the Phase II pilot handlers into the process-wide registry.

    R0 handlers are never registered — an unregistered anomaly type is R0 by
    default (observe-only), which is the safe default.
    """
    registry.register(BeatTaskRetryHandler())


# Kept for symmetry / documentation of the safe default.
__all__ = ["BeatTaskRetryHandler", "register_default_handlers", "R0", "R1"]
