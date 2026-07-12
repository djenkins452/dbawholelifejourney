"""
WLJ Operations — audit model (Phase II).

``RecoveryAttempt`` is the atomic audit unit of the recovery lifecycle
(WLJ_OPERATIONS_VISION.md §9 canonical object · §5 lifecycle). EVERY path through
the lifecycle writes a row — including "unsafe, skipped" and "cooldown, skipped" —
so the audit is a complete, deterministic, queryable history (Principle 10).

The model is a subpackage of the ``core`` Django app (like ``ai_observability``),
so it declares ``app_label = "core"`` and its migration lives in
``apps/core/migrations/``. It is imported for registration from
``apps/core/models.py`` (a non-request-path module — import-boundary safe).
"""
from __future__ import annotations

from django.db import models


class RecoveryAttempt(models.Model):
    """One execution of the recovery lifecycle for a single incident.

    Recovery NEVER writes incident state (``OpsAnomaly.is_active``). The SAME
    detector/reconcile pipeline is the single authority for incident lifecycle
    (Constitution III.1/III.2): recovery drives the condition toward healthy and
    proves it with the detector's own predicate; the reconcile pipeline then
    resolves the incident on its next cycle. This row is the deterministic record
    of what recovery did and what verification observed — it cannot manufacture a
    healthy state.
    """

    # ── Lifecycle phase (which step of §5 produced this row) ──────────────
    PHASE_DIAGNOSED = "DIAGNOSED"
    PHASE_RECOVER_ATTEMPTED = "RECOVER_ATTEMPTED"
    PHASE_VERIFIED = "VERIFIED"
    PHASE_CLOSED = "CLOSED"
    PHASE_ESCALATED = "ESCALATED"
    PHASE_SKIPPED_COOLDOWN = "SKIPPED_COOLDOWN"
    PHASE_SKIPPED_UNSAFE = "SKIPPED_UNSAFE"
    # Shadow Mode: a SIMULATED decision — the engine ran the full deterministic
    # lifecycle and recorded what it WOULD have done, then stopped before acting.
    # This phase is used ONLY for simulated rows, so a shadow record can never be
    # mistaken for a real recovery/verification/escalation (mode is SHADOW too).
    PHASE_SHADOW = "SHADOW"
    PHASE_CHOICES = [
        (PHASE_DIAGNOSED, "Diagnosed"),
        (PHASE_RECOVER_ATTEMPTED, "Recover attempted"),
        (PHASE_VERIFIED, "Verified healthy"),
        (PHASE_CLOSED, "Incident closed (verified)"),
        (PHASE_ESCALATED, "Escalated to engineering"),
        (PHASE_SKIPPED_COOLDOWN, "Skipped — cooldown"),
        (PHASE_SKIPPED_UNSAFE, "Skipped — unsafe classification"),
        (PHASE_SHADOW, "Shadow — simulated only (no action)"),
    ]

    # ── Outcome ───────────────────────────────────────────────────────────
    OUTCOME_SUCCESS = "SUCCESS"
    OUTCOME_FAILED = "FAILED"
    OUTCOME_PENDING = "PENDING_VERIFICATION"
    OUTCOME_SHADOW = "SHADOW_SIMULATED"  # a shadow decision — nothing was executed
    OUTCOME_CHOICES = [
        (OUTCOME_SUCCESS, "Success"),
        (OUTCOME_FAILED, "Failed"),
        (OUTCOME_PENDING, "Pending verification"),
        (OUTCOME_SHADOW, "Shadow (simulated — no action taken)"),
    ]

    # ── Execution mode this row was written under (Shadow-Mode validation) ─
    # ACTIVE = a real recovery decision that executed (or gated) for real.
    # SHADOW = a simulated decision (engine stopped before acting).
    # Pre-existing rows default to ACTIVE (they were all written by live recovery).
    MODE_ACTIVE = "ACTIVE"
    MODE_SHADOW = "SHADOW"
    MODE_CHOICES = [
        (MODE_ACTIVE, "Active (real)"),
        (MODE_SHADOW, "Shadow (simulated)"),
    ]

    # Recovery safety classification at the time of action (vision §4).
    CLASSIFICATION_CHOICES = [
        ("R0", "R0 — Observe only"),
        ("R1", "R1 — Safe idempotent"),
        ("R2", "R2 — Low-risk service"),
        ("R3", "R3 — Stateful (approval)"),
        ("R4", "R4 — Destructive (engineering)"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Last-write time (audit). For a deferred-verification row this is the moment
    # the pending attempt was RESOLVED (verified/failed), so a recovery's duration
    # is deterministically ``updated_at - created_at`` with no engine-logic change.
    # Nullable so the additive migration needs no one-off default for historical rows.
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    # Reconciliation identity of the incident this attempt targets. We store the
    # anomaly's stable (anomaly_type, engine_name) key rather than a hard FK so an
    # attempt's audit survives the incident being resolved (and re-raised) by the
    # SAME reconcile pipeline. ``anomaly_id`` is a soft reference (may be null once
    # the incident is resolved).
    anomaly_id = models.IntegerField(null=True, blank=True)
    anomaly_type = models.CharField(max_length=25)
    engine_name = models.CharField(max_length=128, blank=True, default="")

    monitor_key = models.CharField(
        max_length=64,
        help_text="Recovery handler that owns this attempt (e.g. 'scheduled_task').",
    )
    classification = models.CharField(max_length=2, choices=CLASSIFICATION_CHOICES)
    phase = models.CharField(max_length=24, choices=PHASE_CHOICES)
    outcome = models.CharField(
        max_length=24, choices=OUTCOME_CHOICES, blank=True, default=""
    )
    # Execution mode: ACTIVE (real) or SHADOW (simulated). Additive; existing rows
    # default ACTIVE. Lets the audit + Command Center distinguish shadow decisions
    # from real recovery beyond doubt (belt-and-braces with PHASE_SHADOW).
    mode = models.CharField(
        max_length=8, choices=MODE_CHOICES, default=MODE_ACTIVE, db_index=True
    )

    attempt_number = models.PositiveIntegerField(default=1)
    action_taken = models.TextField(
        blank=True, default="", help_text="Deterministic description of the action."
    )

    # Detection-signal snapshots proving the before/after state (verification
    # reuses the observability detector predicate — never a looser bar).
    evidence_before = models.JSONField(default=dict, blank=True)
    evidence_after = models.JSONField(default=dict, blank=True)

    error = models.TextField(
        blank=True, default="", help_text="Captured exception text (never swallowed)."
    )

    class Meta:
        app_label = "core"
        db_table = "core_recovery_attempt"
        ordering = ["-created_at"]
        indexes = [
            # Cooldown / retry / recurrence are all computed from these rows.
            models.Index(
                fields=["anomaly_type", "engine_name", "-created_at"],
                name="idx_recovery_key",
            ),
            models.Index(fields=["outcome", "-created_at"], name="idx_recovery_outcome"),
        ]

    def __str__(self):
        return (
            f"RecoveryAttempt({self.monitor_key} {self.anomaly_type}/{self.engine_name} "
            f"#{self.attempt_number} {self.phase}/{self.outcome})"
        )
