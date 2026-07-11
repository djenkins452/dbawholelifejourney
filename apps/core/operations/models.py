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
    PHASE_CHOICES = [
        (PHASE_DIAGNOSED, "Diagnosed"),
        (PHASE_RECOVER_ATTEMPTED, "Recover attempted"),
        (PHASE_VERIFIED, "Verified healthy"),
        (PHASE_CLOSED, "Incident closed (verified)"),
        (PHASE_ESCALATED, "Escalated to engineering"),
        (PHASE_SKIPPED_COOLDOWN, "Skipped — cooldown"),
        (PHASE_SKIPPED_UNSAFE, "Skipped — unsafe classification"),
    ]

    # ── Outcome ───────────────────────────────────────────────────────────
    OUTCOME_SUCCESS = "SUCCESS"
    OUTCOME_FAILED = "FAILED"
    OUTCOME_PENDING = "PENDING_VERIFICATION"
    OUTCOME_CHOICES = [
        (OUTCOME_SUCCESS, "Success"),
        (OUTCOME_FAILED, "Failed"),
        (OUTCOME_PENDING, "Pending verification"),
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
