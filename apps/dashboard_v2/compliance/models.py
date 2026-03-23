"""
ComplianceEvent — canonical audit model for tracked commitments.

Every item that WLJ tracks as expected/completed/missed gets exactly one
ComplianceEvent row per user per day per item. This is the single source
of truth that summary cards, drill-down UIs, signals, and Beth read from.

Architecture rule:
    raw data → domain adapters → ComplianceEvent → rollup / detail / signal
"""

from django.conf import settings
from django.db import models

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_STATUS_CHOICES,
    DOMAIN_CHOICES,
    FINAL_STATUS_CHOICES,
    REASON_CODE_CHOICES,
    SCORING_BUCKET_CHOICES,
)


class ComplianceEvent(models.Model):
    """
    One row per tracked item per user per date.

    Immutable once created for a given evaluation window. Re-evaluation
    replaces old rows (delete + recreate) for the same user/date/domain/item.
    """

    # ── Identity ──
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="compliance_events",
    )
    event_date = models.DateField(
        db_index=True,
        help_text="The date this expectation applies to",
    )

    # ── Classification ──
    domain = models.CharField(
        max_length=30,
        choices=DOMAIN_CHOICES,
        help_text="Source domain (medication, workout, routine, task, journal, faith)",
    )
    scoring_bucket = models.CharField(
        max_length=30,
        choices=SCORING_BUCKET_CHOICES,
        help_text="Which V2 summary card this event rolls into",
    )

    # ── Item identification ──
    item_type = models.CharField(
        max_length=50,
        help_text="Model name or type identifier (e.g., 'MedicineSchedule', 'Task')",
    )
    item_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="PK of the source record (schedule, task, etc.)",
    )
    item_label = models.CharField(
        max_length=255,
        help_text="Human-readable item name for display",
    )

    # ── Timing ──
    expected_at = models.TimeField(
        null=True,
        blank=True,
        help_text="When this item was expected (scheduled time)",
    )

    # ── Status chain ──
    expected = models.BooleanField(
        default=True,
        help_text="Was this item expected/due on this date?",
    )
    actual_status = models.CharField(
        max_length=20,
        choices=ACTUAL_STATUS_CHOICES,
        help_text="What actually happened",
    )
    final_status = models.CharField(
        max_length=20,
        choices=FINAL_STATUS_CHOICES,
        help_text="Scoring status after applying rules",
    )

    # ── Explainability ──
    reason_code = models.CharField(
        max_length=40,
        choices=REASON_CODE_CHOICES,
        help_text="Why this item received its final_status",
    )
    reason_detail = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context: grace period, linked items, metadata",
    )

    # ── Source tracking ──
    source_system = models.CharField(
        max_length=50,
        help_text="Which model/system produced this event",
    )

    # ── Relationships (for dedupe) ──
    related_event = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_events",
        help_text="If this event was satisfied by another event",
    )

    # ── Obligation reconciliation ──
    obligation_type = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text=(
            "Obligation category: workout, journal, faith_prayer, faith_bible, "
            "medication, task. Events with the same type+identity+date are one obligation."
        ),
    )
    obligation_identity = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Stable identifier within obligation_type. "
            "e.g., WorkoutSchedule PK, MedicineSchedule PK, Task PK. "
            "Combined with type+user+date to form obligation_key."
        ),
    )
    obligation_key = models.CharField(
        max_length=200,
        blank=True,
        default="",
        db_index=True,
        help_text=(
            "Deterministic key: {type}:{user_id}:{date}:{identity}. "
            "Events sharing a key are reconciled so only one is score-bearing."
        ),
    )
    is_primary = models.BooleanField(
        default=True,
        help_text=(
            "True if this event counts toward rollup scoring. "
            "Suppressed duplicates have is_primary=False."
        ),
    )
    suppression_reason = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Why this event was suppressed from scoring (empty = not suppressed)",
    )

    # ── Timestamps ──
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_date", "expected_at"]
        indexes = [
            models.Index(fields=["user", "event_date"]),
            models.Index(fields=["user", "scoring_bucket", "event_date"]),
            models.Index(fields=["user", "domain", "event_date"]),
            models.Index(fields=["user", "final_status", "event_date"]),
            models.Index(fields=["user", "obligation_key"]),
        ]

    def __str__(self):
        return (
            f"{self.event_date} | {self.domain} | {self.item_label} | "
            f"{self.final_status} ({self.reason_code})"
        )

    @property
    def reason_label(self):
        """Human-readable explanation of why this status was assigned."""
        from apps.dashboard_v2.compliance.constants import REASON_LABELS
        return REASON_LABELS.get(self.reason_code, self.reason_code)

    @property
    def final_status_label(self):
        """Human-readable final status."""
        from apps.dashboard_v2.compliance.constants import FINAL_STATUS_LABELS
        return FINAL_STATUS_LABELS.get(self.final_status, self.final_status)

    @property
    def suppression_label(self):
        """Human-readable suppression explanation."""
        from apps.dashboard_v2.compliance.constants import SUPPRESSION_LABELS
        return SUPPRESSION_LABELS.get(self.suppression_reason, "")

    @property
    def is_suppressed(self):
        """True if this event is suppressed from scoring."""
        return not self.is_primary and bool(self.suppression_reason)
