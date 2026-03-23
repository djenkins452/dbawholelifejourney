"""
Phase 4 — Signal Feedback & Execution Quality Signals.

SignalFeedback: Captures user confirmation/rejection of behavioral signals.
ExecutionSignal: Read-only analytical layer tracking execution quality
    (on-target, late, missed-window, missed) for scheduled items.

ARCHITECTURAL RULES:
- These models store analytical data only — no decision logic
- No updates to execution truth here
- No side effects beyond storing the record
- ExecutionSignal does NOT affect UI, CoS, or completion logic
"""

from django.conf import settings
from django.db import models


class SignalFeedback(models.Model):
    """Records explicit user feedback on a behavioral signal.

    Each record captures a single yes/no response to a signal
    presented by the system (via Beth or UI).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signal_feedback",
    )
    signal_type = models.CharField(
        max_length=50,
        help_text="Signal type: possible_completion, effort_signal, etc.",
    )
    domain = models.CharField(
        max_length=50,
        help_text="Domain: faith, health, journal, purpose.",
    )
    item = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Specific item: prayer, workout, journal_entry, etc.",
    )
    fingerprint = models.CharField(
        max_length=255,
        help_text="Unique signal identity: {type}:{domain}:{item}:{date}",
    )
    response = models.CharField(
        max_length=10,
        choices=[
            ("yes", "Yes"),
            ("no", "No"),
        ],
    )
    source = models.CharField(
        max_length=50,
        help_text="Where the signal was detected: journal, workout_notes, etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["fingerprint"]),
        ]

    def __str__(self):
        return (
            f"SignalFeedback({self.user_id}, {self.signal_type}, "
            f"{self.domain}, {self.response})"
        )


class ExecutionSignal(models.Model):
    """Read-only analytical record of execution quality for a scheduled item.

    Tracks whether scheduled items were completed on-target, late,
    within a missed window, or fully missed. This is a pure analytical
    layer — it does NOT affect completion logic, CoS, or UI.

    Created/updated when completion events fire (RoutineLog, WorkoutSession,
    JournalEntry, MedicineLog) or when the missed-detection sweep runs.
    """

    ON_TARGET = "on_target"
    LATE = "late"
    MISSED_WINDOW = "missed_window"
    MISSED = "missed"

    QUALITY_CHOICES = [
        (ON_TARGET, "On Target"),
        (LATE, "Late"),
        (MISSED_WINDOW, "Missed Window"),
        (MISSED, "Missed"),
    ]

    DOMAIN_ROUTINE = "routine"
    DOMAIN_WORKOUT = "workout"
    DOMAIN_JOURNAL = "journal"
    DOMAIN_MEDICINE = "medicine"

    DOMAIN_CHOICES = [
        (DOMAIN_ROUTINE, "Routine"),
        (DOMAIN_WORKOUT, "Workout"),
        (DOMAIN_JOURNAL, "Journal"),
        (DOMAIN_MEDICINE, "Medicine"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_signals",
    )
    item_name = models.CharField(
        max_length=200,
        help_text="Name of the scheduled item (routine item name, medicine name, etc.)",
    )
    domain_type = models.CharField(
        max_length=20,
        choices=DOMAIN_CHOICES,
        help_text="Which domain this item belongs to.",
    )
    scheduled_time = models.DateTimeField(
        help_text="When the item was scheduled to happen.",
    )
    actual_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the item was actually completed. Null if missed.",
    )
    execution_quality = models.CharField(
        max_length=20,
        choices=QUALITY_CHOICES,
        help_text="Quality assessment of execution timing.",
    )
    date = models.DateField(
        help_text="The date this signal applies to.",
    )
    source_model = models.CharField(
        max_length=50,
        blank=True,
        help_text="Model that triggered this signal (e.g., RoutineLog, MedicineLog).",
    )
    source_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="PK of the source object.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "domain_type", "date"]),
            models.Index(fields=["execution_quality"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "item_name", "domain_type", "date"],
                name="unique_execution_signal_per_item_day",
            ),
        ]

    def __str__(self):
        return (
            f"ExecutionSignal({self.user_id}, {self.item_name}, "
            f"{self.domain_type}, {self.execution_quality}, {self.date})"
        )
