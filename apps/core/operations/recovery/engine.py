"""
WLJ Operations — Recovery Engine (Phase II).

Runs the Standard Recovery Lifecycle (WLJ_OPERATIONS_VISION.md §5) over active
incidents, in the background worker, strictly downstream of the telemetry cycle.

Non-negotiable invariants:
  * Recovery NEVER writes incident state (``OpsAnomaly.is_active``). The SAME
    detector/reconcile pipeline is the single authority for incident lifecycle
    (Constitution III.1/III.2). Recovery drives the condition toward healthy and
    proves it with the detector's own predicate; the reconcile pipeline resolves
    the incident on its next cycle. Recovery therefore *cannot* manufacture a
    healthy state — it has no write access to it.
  * Only a passing verification (the detector predicate) counts a recovery as
    successful. Verification always follows recover; nothing closes optimistically.
  * Every meaningful lifecycle decision is audited (RecoveryAttempt). Transient
    "waiting" ticks (cooldown / pending) are intentionally NOT written each 60s —
    that would flood the audit (risk R-8) without recording a decision.
  * Bounded: finite max_attempts (R1 included), cooldown, and a recurrence limit
    that raises a permanent-fix escalation instead of masking a recurring class.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.operations.models import RecoveryAttempt
from apps.core.operations.recovery.base import RecoveryDiagnosis, registry
from apps.core.operations.recovery.handlers import register_default_handlers
from apps.core.operations.recovery.mode import (
    ACTIVE,
    DISABLED,
    SHADOW,
    get_recovery_mode,
)

logger = logging.getLogger(__name__)

_HANDLERS_READY = False


def _ensure_handlers():
    global _HANDLERS_READY
    if not _HANDLERS_READY:
        register_default_handlers()
        _HANDLERS_READY = True


def _audit(anomaly, handler, phase, *, classification, outcome="",
           attempt_number=1, action="", before=None, after=None, error="",
           mode=RecoveryAttempt.MODE_ACTIVE):
    return RecoveryAttempt.objects.create(
        anomaly_id=getattr(anomaly, "id", None),
        anomaly_type=anomaly.anomaly_type,
        engine_name=anomaly.engine_name or "",
        monitor_key=handler.monitor_key,
        classification=classification,
        phase=phase,
        outcome=outcome,
        attempt_number=attempt_number,
        action_taken=action or "",
        evidence_before=before or {},
        evidence_after=after or {},
        error=error or "",
        mode=mode,
    )


def run_recovery_cycle(now=None) -> dict:
    """Process every active incident that has a registered recovery handler.

    Three modes (WLJ_OPERATIONS_VISION.md §4a Recovery Mode):
      * DISABLED → a true no-op (no diagnosis/action/verification/audit).
      * SHADOW   → run the FULL deterministic lifecycle, then STOP before acting;
        record one distinct SHADOW audit row per incident (what recovery WOULD do).
      * ACTIVE   → real recovery (unchanged behaviour).

    Returns a deterministic summary (also used by the recovery telemetry section).
    """
    mode = get_recovery_mode()
    if mode == DISABLED:
        return {"enabled": False, "mode": DISABLED, "processed": 0}

    from apps.core.ai_observability.models import OpsAnomaly

    _ensure_handlers()
    now = now or timezone.now()
    shadow = mode == SHADOW
    summary = {
        "enabled": True, "mode": mode, "processed": 0, "recovered": 0,
        "verified": 0, "escalated": 0, "skipped_unsafe": 0, "waiting": 0,
        "errors": 0, "locked_skipped": 0,
        # Shadow-only counters (0 in ACTIVE mode):
        "shadowed": 0, "would_recover": 0, "would_observe": 0,
    }

    # Snapshot the candidate incident ids first, then process each under a
    # per-incident row lock (below). Cheap; active anomalies are few.
    active_ids = list(
        OpsAnomaly.objects.filter(is_active=True).values_list("pk", flat=True)
    )
    for pk in active_ids:
        _process_locked(pk, now, summary, shadow)

    return summary


def _process_locked(pk, now, summary, shadow=False):
    """Process one incident under a DURABLE per-incident DB row lock.

    Concurrency protection (beyond the audit-record cooldown/pending checks): each
    incident is re-fetched with ``SELECT … FOR UPDATE SKIP LOCKED`` inside its own
    transaction, so two overlapping recovery cycles (or two workers) can never act
    on the SAME incident — the second cycle finds the row locked and skips it. The
    RecoveryAttempt audit rows are written inside this transaction, so the
    pending/attempt record is durably committed with the lock, closing the
    read-decide-act (TOCTOU) window. On Postgres this is a real row lock; the
    recovery worker is the only writer of these attempts.
    """
    from apps.core.ai_observability.models import OpsAnomaly

    try:
        with transaction.atomic():
            anomaly = (
                OpsAnomaly.objects
                .select_for_update(skip_locked=True)
                .filter(pk=pk, is_active=True)
                .first()
            )
            if anomaly is None:
                # Locked by another cycle/worker (skip_locked) or resolved meanwhile.
                summary["locked_skipped"] += 1
                return
            handler = registry.handler_for(anomaly.anomaly_type)
            if handler is None:
                return  # no handler → R0 (observe-only), the safe default
            summary["processed"] += 1
            _process_incident(anomaly, handler, now, summary, shadow)
    except Exception as e:  # never swallow — audit + log, continue with the rest
        summary["errors"] += 1
        logger.error(
            "Recovery: incident %s failed: %s", pk, e, exc_info=True,
        )
        try:
            from apps.core.ai_observability.models import OpsAnomaly as _OA
            a = _OA.objects.filter(pk=pk).first()
            h = registry.handler_for(a.anomaly_type) if a else None
            if a is not None and h is not None:
                # In SHADOW a failure is a simulated failure — it must NEVER surface
                # as a real escalation (which pages engineering). Record it as a
                # SHADOW row instead, so shadow can never mutate real recovery state.
                if shadow:
                    _audit(a, h, RecoveryAttempt.PHASE_SHADOW,
                           classification=h.policy.classification,
                           outcome=RecoveryAttempt.OUTCOME_SHADOW,
                           action="SHADOW: simulation raised — no action taken.",
                           error=str(e), mode=RecoveryAttempt.MODE_SHADOW)
                else:
                    _audit(a, h, RecoveryAttempt.PHASE_ESCALATED,
                           classification=h.policy.classification,
                           outcome=RecoveryAttempt.OUTCOME_FAILED,
                           action="Handler raised — escalated.", error=str(e))
        except Exception:  # pragma: no cover - audit best-effort
            logger.error("Recovery: failed to audit handler error", exc_info=True)


def _attempts_for(anomaly, since=None):
    qs = RecoveryAttempt.objects.filter(
        anomaly_type=anomaly.anomaly_type, engine_name=anomaly.engine_name or "",
    )
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    return qs


def _verification_predicate(handler) -> str:
    """Name of the deterministic predicate ``verify()`` reuses (never executed here)."""
    return getattr(handler, "verification_predicate", "") or f"{handler.__class__.__name__}.verify"


def _shadow_evaluate(anomaly, handler, now, summary):
    """SHADOW mode: run the deterministic decision, record what recovery WOULD do,
    then STOP. No ``recover()``, no ``verify()``, no state mutation, no incident
    closure, no side effect — only a single distinct SHADOW audit row.

    Idempotent per incident occurrence (one SHADOW row since ``anomaly.created_at``),
    so a 60s cycle cadence never floods the audit (risk R-8). The decision is stable
    within an occurrence because shadow writes no RECOVER_ATTEMPTED rows, so cooldown/
    retry counters never advance — shadow answers "right now, would recovery act?".
    """
    policy = handler.policy

    already = _attempts_for(anomaly, since=anomaly.created_at).filter(
        phase=RecoveryAttempt.PHASE_SHADOW
    ).exists()
    if already:
        summary["shadowed"] += 1  # counted, not re-written (audit-volume guard)
        return

    # diagnose() is contractually side-effect-free — safe to call in shadow.
    diagnosis = handler.diagnose(anomaly)
    predicate = _verification_predicate(handler)

    if not diagnosis.recoverable or not policy.auto_executable:
        would_execute = False
        classification = "R0"
        decision = "observe_only"
        action = f"SHADOW: would observe only (R0) — {diagnosis.reason}"
        summary["would_observe"] += 1
    else:
        would_execute = True
        classification = policy.classification
        decision = "recover"
        action = (
            f"SHADOW: would {handler.describe_action(diagnosis)} "
            f"({classification}); verify via {predicate}"
        )
        summary["would_recover"] += 1

    _audit(
        anomaly, handler, RecoveryAttempt.PHASE_SHADOW,
        classification=classification,
        outcome=RecoveryAttempt.OUTCOME_SHADOW,
        action=action,
        before={
            **(diagnosis.evidence or {}),
            "shadow": True,
            "would_execute": would_execute,
            "decision": decision,
            "verification_predicate": predicate,
            "recovery_action": handler.describe_action(diagnosis) if would_execute else None,
            "skipped_because": "Shadow Mode — simulated only",
        },
        mode=RecoveryAttempt.MODE_SHADOW,
    )
    summary["shadowed"] += 1


def _process_incident(anomaly, handler, now, summary, shadow=False):
    if shadow:
        # Stop before ANY action: full deterministic decision, recorded, no execute.
        _shadow_evaluate(anomaly, handler, now, summary)
        return

    policy = handler.policy
    cooldown = timedelta(seconds=policy.cooldown_seconds)

    # ── 1) Resolve any pending (deferred) verification first ──────────────
    pending = (
        _attempts_for(anomaly)
        .filter(outcome=RecoveryAttempt.OUTCOME_PENDING)
        .order_by("-created_at")
        .first()
    )
    if pending is not None:
        if now - pending.created_at < cooldown:
            summary["waiting"] += 1
            return  # give the async effect time to land; re-check next cycle
        vr = handler.verify(RecoveryDiagnosis(target=anomaly.engine_name or "", reason=""))
        pending.outcome = (
            RecoveryAttempt.OUTCOME_SUCCESS if vr.healthy
            else RecoveryAttempt.OUTCOME_FAILED
        )
        pending.evidence_after = vr.evidence
        pending.phase = (
            RecoveryAttempt.PHASE_VERIFIED if vr.healthy else RecoveryAttempt.PHASE_RECOVER_ATTEMPTED
        )
        pending.save(update_fields=["outcome", "evidence_after", "phase"])
        if vr.healthy:
            summary["verified"] += 1
            if not anomaly.is_active:
                _audit(anomaly, handler, RecoveryAttempt.PHASE_CLOSED,
                       classification=policy.classification,
                       outcome=RecoveryAttempt.OUTCOME_SUCCESS,
                       action="Condition cleared; incident resolved by reconcile pipeline.",
                       after=vr.evidence)
            return
        # not healthy → fall through to retry/escalate decision below

    # ── 2) Gate on classification / recoverability ────────────────────────
    diagnosis = handler.diagnose(anomaly)
    if not diagnosis.recoverable or not policy.auto_executable:
        # Observe-only for this target (R0). Record the decision ONCE per incident
        # occurrence — never every 60s (audit-volume guard, R-8).
        already = _attempts_for(anomaly, since=anomaly.created_at).filter(
            phase=RecoveryAttempt.PHASE_SKIPPED_UNSAFE
        ).exists()
        if not already:
            summary["skipped_unsafe"] += 1
            _audit(anomaly, handler, RecoveryAttempt.PHASE_SKIPPED_UNSAFE,
                   classification="R0", outcome=RecoveryAttempt.OUTCOME_FAILED,
                   action=diagnosis.reason, before=diagnosis.evidence)
        return

    # ── 3) Recurrence → permanent-fix escalation ("eliminate the class") ──
    if policy.recurrence_limit:
        window_start = now - timedelta(hours=policy.recurrence_window_hours)
        successes = _attempts_for(anomaly, since=window_start).filter(
            outcome=RecoveryAttempt.OUTCOME_SUCCESS,
            phase=RecoveryAttempt.PHASE_VERIFIED,
        ).count()
        if successes >= policy.recurrence_limit:
            self_escalated = _attempts_for(anomaly, since=window_start).filter(
                phase=RecoveryAttempt.PHASE_ESCALATED
            ).exists()
            if not self_escalated:
                summary["escalated"] += 1
                _audit(anomaly, handler, RecoveryAttempt.PHASE_ESCALATED,
                       classification=policy.classification,
                       outcome=RecoveryAttempt.OUTCOME_FAILED,
                       action=(f"Recovered {successes}× in {policy.recurrence_window_hours}h "
                               "— recurring class; needs permanent fix."),
                       before=diagnosis.evidence)
            return

    # ── 4) Retry bound (per incident occurrence) ──────────────────────────
    attempts_made = _attempts_for(anomaly, since=anomaly.created_at).filter(
        phase=RecoveryAttempt.PHASE_RECOVER_ATTEMPTED
    ).count()
    if attempts_made >= policy.max_attempts:
        exhausted_escalated = _attempts_for(anomaly, since=anomaly.created_at).filter(
            phase=RecoveryAttempt.PHASE_ESCALATED
        ).exists()
        if not exhausted_escalated:
            summary["escalated"] += 1
            _audit(anomaly, handler, RecoveryAttempt.PHASE_ESCALATED,
                   classification=policy.classification,
                   outcome=RecoveryAttempt.OUTCOME_FAILED,
                   action=f"Recovery exhausted after {attempts_made} attempt(s) — needs engineering.",
                   before=diagnosis.evidence)
        return

    # ── 5) Cooldown (wait silently; not a lifecycle decision) ─────────────
    last_attempt = _attempts_for(anomaly).filter(
        phase=RecoveryAttempt.PHASE_RECOVER_ATTEMPTED
    ).order_by("-created_at").first()
    if last_attempt is not None and now - last_attempt.created_at < cooldown:
        summary["waiting"] += 1
        return

    # ── 6) Act: recover, then verify (deferred if async) ──────────────────
    outcome = handler.recover(diagnosis)
    attempt_number = attempts_made + 1
    summary["recovered"] += 1
    row = _audit(anomaly, handler, RecoveryAttempt.PHASE_RECOVER_ATTEMPTED,
                 classification=policy.classification,
                 outcome=RecoveryAttempt.OUTCOME_PENDING,
                 attempt_number=attempt_number, action=outcome.action_taken,
                 before=diagnosis.evidence, after=outcome.evidence)
    if not outcome.verification_deferred:
        vr = handler.verify(diagnosis)
        row.outcome = (
            RecoveryAttempt.OUTCOME_SUCCESS if vr.healthy
            else RecoveryAttempt.OUTCOME_FAILED
        )
        row.phase = (
            RecoveryAttempt.PHASE_VERIFIED if vr.healthy
            else RecoveryAttempt.PHASE_RECOVER_ATTEMPTED
        )
        row.evidence_after = {**(outcome.evidence or {}), **vr.evidence}
        row.save(update_fields=["outcome", "phase", "evidence_after"])
        if vr.healthy:
            summary["verified"] += 1
