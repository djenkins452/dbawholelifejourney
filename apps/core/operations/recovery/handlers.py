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


def _engine_allowlist() -> frozenset[str]:
    """Operator allowlist of engine names eligible for re-trigger recovery (empty default)."""
    raw = getattr(settings, "OPS_RECOVERY_ENGINE_ALLOWLIST", ()) or ()
    return frozenset(str(x) for x in raw)


class BeatTaskRetryHandler(RecoveryHandler):
    """R1 — re-enqueue an allowlisted, idempotent Beat task that OPS-1 flagged MISSED."""

    monitor_key = "scheduled_task"
    handled_anomaly_types = frozenset({"MISSED_RUN"})
    verification_predicate = "compute_scheduled_task_states (OPS-1 freshness)"
    policy = RecoveryPolicy(
        classification=R1,
        max_attempts=2,          # finite even for R1 — no unbounded loop
        cooldown_seconds=120,    # ≥ typical short cadence; anti-thrash
        recurrence_window_hours=24,
        recurrence_limit=5,      # keeps missing → permanent-fix escalation
    )

    def describe_action(self, diagnosis: RecoveryDiagnosis) -> str:
        return f"re-enqueue Beat task '{diagnosis.target}'"

    def is_enabled(self) -> bool:
        return bool(getattr(settings, "OPS_RECOVERY_BEAT_RETRY", False))

    def allowlist_size(self) -> int:
        return len(_beat_retry_allowlist())

    def diagnose(self, anomaly) -> RecoveryDiagnosis:
        task_name = (anomaly.engine_name or "").strip()
        allow = task_name in _beat_retry_allowlist()
        enabled = self.is_enabled()
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


class EngineStarvationRetriggerHandler(RecoveryHandler):
    """R1 (re-trigger shape) — re-run a starved engine that ENGINE_STARVATION flagged.

    Shares the exact shape as ``BeatTaskRetryHandler`` (re-trigger a scheduled unit of
    work; verify via its freshness predicate) but for registered engines rather than
    Beat tasks. Verification is DEFERRED (the re-run is async). This is the SOLE
    engine re-run path: the legacy in-SAME ``_run_autonomous_remediation`` auto-rerun
    was proven inert (its P3 filter never matched P1/P2 MISSED_RUN/SUPPRESSION_STORM)
    and removed under OPS-11 (2026-07-12). Allowlisted + flagged; empty/off by default.
    """

    monitor_key = "engine"
    handled_anomaly_types = frozenset({"ENGINE_STARVATION"})
    verification_predicate = "engine_ran_within_24h (starvation inverse)"
    policy = RecoveryPolicy(
        classification=R1,
        max_attempts=2,
        cooldown_seconds=300,       # engines run on minute+ cadences
        recurrence_window_hours=24,
        recurrence_limit=4,         # keeps starving → the scheduler needs a permanent fix
    )

    def describe_action(self, diagnosis: RecoveryDiagnosis) -> str:
        return f"re-trigger engine '{diagnosis.target}'"

    def is_enabled(self) -> bool:
        return bool(getattr(settings, "OPS_RECOVERY_ENGINE_RETRIGGER", False))

    def allowlist_size(self) -> int:
        return len(_engine_allowlist())

    def diagnose(self, anomaly) -> RecoveryDiagnosis:
        from apps.core.ai_observability.engine_registry import get_engine_meta

        engine = (anomaly.engine_name or "").strip()
        allow = engine in _engine_allowlist()
        enabled = self.is_enabled()
        meta = get_engine_meta(engine)
        can_run = bool(meta and meta.get("can_manual_run"))
        recoverable = allow and enabled and can_run
        return RecoveryDiagnosis(
            target=engine,
            reason=(
                f"Engine '{engine}' is STARVED (no runs in 24h)."
                + ("" if recoverable else " Not allowlisted/enabled/runnable → observe-only (R0).")
            ),
            evidence={
                "engine": engine, "allowlisted": allow,
                "handler_enabled": enabled, "can_manual_run": can_run,
            },
            recoverable=recoverable,
        )

    def recover(self, diagnosis: RecoveryDiagnosis) -> RecoveryOutcome:
        """Re-trigger the engine via the deterministic by-name runner (idempotent,
        guarded by is_engine_active). The run is async → verification deferred."""
        from apps.core.ai_observability.models import EngineExecutionLog
        from apps.core.celery_utils import safe_enqueue
        from apps.core.tasks import run_engine_task

        engine = diagnosis.target
        if EngineExecutionLog.is_engine_active(engine):
            # Already running — nothing to do; let verification confirm freshness.
            return RecoveryOutcome(
                action_taken=f"Engine '{engine}' already active; no re-trigger needed.",
                verification_deferred=True,
                evidence={"skipped": "already_active"},
            )
        execution = EngineExecutionLog.objects.create(
            engine_name=engine, trigger_source="ops_recovery", status="queued",
            triggered_by=None,
        )
        enqueued = safe_enqueue(run_engine_task, engine, execution.id)
        return RecoveryOutcome(
            action_taken=(
                f"Re-triggered engine '{engine}' (execution_id={execution.id})"
                + ("" if enqueued else " (broker unavailable — enqueue failed)")
            ),
            verification_deferred=enqueued,
            evidence={"enqueued": enqueued, "execution_id": execution.id},
        )

    def verify(self, diagnosis: RecoveryDiagnosis) -> VerificationResult:
        """Healthy iff the engine has produced a run in the last 24h — the exact
        inverse of the ENGINE_STARVATION detector predicate."""
        from apps.core.ai_observability.same_engine import engine_ran_within_24h

        engine = diagnosis.target
        ran = engine_ran_within_24h(engine)
        return VerificationResult(healthy=ran, evidence={"engine": engine, "ran_24h": ran})


class MaturitySnapshotRefreshHandler(RecoveryHandler):
    """R1 (recompute shape) — recompute a stale system maturity snapshot.

    A DIFFERENT shape from the re-trigger handlers: the recompute runs SYNCHRONOUSLY
    in the recovery worker (background — heavy compute is fine off the request path),
    so verification is IMMEDIATE (not deferred). The maturity snapshot is a 24h ISE
    job, independent of SAME and Beat, so this fills a real gap (corrects ADR-17 for
    this snapshot). Flagged; off by default.
    """

    monitor_key = "maturity_snapshot"
    handled_anomaly_types = frozenset({"MATURITY_SNAPSHOT_STALE"})
    verification_predicate = "maturity_snapshot_age_days < threshold (staleness inverse)"
    policy = RecoveryPolicy(
        classification=R1,
        max_attempts=2,
        cooldown_seconds=300,
        recurrence_window_hours=48,
        recurrence_limit=3,         # keeps going stale → ISE schedule needs a permanent fix
    )

    def describe_action(self, diagnosis: RecoveryDiagnosis) -> str:
        return "recompute the system maturity snapshot (daily upsert)"

    def is_enabled(self) -> bool:
        return bool(getattr(settings, "OPS_RECOVERY_MATURITY_SNAPSHOT", False))

    def diagnose(self, anomaly) -> RecoveryDiagnosis:
        enabled = self.is_enabled()
        return RecoveryDiagnosis(
            target="SystemMaturitySnapshot",
            reason=(
                "System maturity snapshot is stale."
                + ("" if enabled else " Handler disabled → observe-only (R0).")
            ),
            evidence={"handler_enabled": enabled},
            recoverable=enabled,
        )

    def recover(self, diagnosis: RecoveryDiagnosis) -> RecoveryOutcome:
        """Recompute the daily snapshot (idempotent update_or_create on today's date).
        Synchronous — verification is immediate, not deferred."""
        from apps.core.ai_observability.maturity_engine import create_daily_snapshot

        create_daily_snapshot()
        return RecoveryOutcome(
            action_taken="Recomputed the system maturity snapshot (daily upsert).",
            verification_deferred=False,
            evidence={},
        )

    def verify(self, diagnosis: RecoveryDiagnosis) -> VerificationResult:
        """Healthy iff the newest snapshot is now within the staleness threshold —
        the exact predicate the detector uses."""
        from apps.core.ai_observability.same_engine import (
            MATURITY_SNAPSHOT_STALE_DAYS,
            maturity_snapshot_age_days,
        )

        age = maturity_snapshot_age_days()
        healthy = age is not None and age < MATURITY_SNAPSHOT_STALE_DAYS
        return VerificationResult(healthy=healthy, evidence={"age_days": age})


def register_default_handlers() -> None:
    """Register the concrete R1 recovery handlers into the process-wide registry.

    R0 handlers are never registered — an unregistered anomaly type is R0 by
    default (observe-only), which is the safe default. Each handler is further gated
    by its own operator flag/allowlist, all off/empty by default (ship-dark).
    """
    registry.register(BeatTaskRetryHandler())
    registry.register(EngineStarvationRetriggerHandler())
    registry.register(MaturitySnapshotRefreshHandler())


def recovery_config_snapshot() -> dict:
    """Deterministic recovery CONFIGURATION facts for the Ops Wall (read-only).

    Single source for "which handlers exist and which operator flags enable them".
    Reads only settings + the process-wide handler registry (no DB, no compute) so
    it is safe to call from the background telemetry cycle. Facts only — never a
    verdict (Constitution I.4). ``register_default_handlers`` is idempotent, so we
    ensure the registry is populated before reading it.
    """
    if len(registry) == 0:
        register_default_handlers()

    handlers = []
    for h in registry.handlers():
        atypes = sorted(h.handled_anomaly_types)
        handlers.append({
            "name": type(h).__name__,
            "monitor_key": h.monitor_key,
            "anomaly_type": atypes[0] if atypes else "",
            "classification": getattr(h.policy, "classification", ""),
            "enabled": h.is_enabled(),
            "allowlist_count": h.allowlist_size(),
        })
    handlers.sort(key=lambda x: x["monitor_key"])

    return {
        "handlers": handlers,
        "handlers_configured": len(handlers),
        "handlers_enabled": sum(1 for h in handlers if h["enabled"]),
        "beat_retry_enabled": bool(getattr(settings, "OPS_RECOVERY_BEAT_RETRY", False)),
        "beat_retry_allowlist_count": len(_beat_retry_allowlist()),
        "engine_retrigger_enabled": bool(getattr(settings, "OPS_RECOVERY_ENGINE_RETRIGGER", False)),
        "engine_allowlist_count": len(_engine_allowlist()),
        "maturity_snapshot_enabled": bool(getattr(settings, "OPS_RECOVERY_MATURITY_SNAPSHOT", False)),
    }


__all__ = [
    "BeatTaskRetryHandler",
    "EngineStarvationRetriggerHandler",
    "MaturitySnapshotRefreshHandler",
    "register_default_handlers",
    "recovery_config_snapshot",
    "R0", "R1",
]
