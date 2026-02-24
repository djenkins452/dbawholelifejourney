"""
CoS v2 Models — Chief of Staff Action Framework

Phase 1 models:
- CosReflection: entity-attached reflections with indefinite retention
- CosPromptSchedule: pre/post event prompt scheduling
- CosGoalSuggestion: goal suggestion throttling + decline tracking
- CosAutoShiftLog: audit trail for automatic event shifts
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


# ──────────────────────────────────────────────────────────
# CosReflection — Entity-attached reflection notes
# ──────────────────────────────────────────────────────────


class CosReflection(TimeStampedModel):
    """
    A reflection note attached to any entity occurrence.

    Reflections are stored indefinitely and used for:
    - Post-activity feedback ("How did your workout go?")
    - Contextual prompts ("Yesterday was tough — how was today?")
    - Pattern detection evidence
    - Long-term memory for the CoS

    Uses Django's GenericForeignKey to attach to any model.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cos_reflections",
    )

    # Generic FK to the source entity (CalendarEvent, JournalEntry, etc.)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the source entity",
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the source entity",
    )
    source_entity = GenericForeignKey("content_type", "object_id")

    # Reflection content
    text = models.TextField(
        help_text="The reflection content (free-text)",
    )
    sentiment = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("negative", "Negative"),
            ("mixed", "Mixed"),
        ],
        help_text="Auto-detected or user-indicated sentiment",
    )

    # Context for temporal comparisons
    activity_date = models.DateField(
        help_text="Date the reflected-upon activity occurred",
    )
    activity_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type of activity (workout, meeting, bible_study, etc.)",
    )

    # Prompt that triggered this reflection (if any)
    prompt_text = models.TextField(
        blank=True,
        help_text="The question/prompt that elicited this reflection",
    )

    class Meta:
        ordering = ["-activity_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["user", "activity_date"],
                name="cos_refl_user_date",
            ),
            models.Index(
                fields=["user", "content_type", "object_id"],
                name="cos_refl_user_entity",
            ),
            models.Index(
                fields=["user", "activity_type", "activity_date"],
                name="cos_refl_user_type_date",
            ),
        ]

    def __str__(self):
        return (
            f"Reflection by user {self.user_id} on "
            f"{self.activity_date} ({self.activity_type})"
        )


# ──────────────────────────────────────────────────────────
# CosPromptSchedule — Pre/post event prompt scheduling
# ──────────────────────────────────────────────────────────


class CosPromptSchedule(TimeStampedModel):
    """
    Scheduled prompt for pre- or post-activity check-ins.

    The ISE (Intelligence Scheduler Engine) scans for due prompts
    and delivers them via DNE (Delivery & Notification Engine).

    Lifecycle: pending → delivered → responded / expired
    """

    TIMING_PRE = "pre"
    TIMING_POST = "post"
    TIMING_CHOICES = [
        (TIMING_PRE, "Pre-activity"),
        (TIMING_POST, "Post-activity"),
    ]

    STATUS_PENDING = "pending"
    STATUS_DELIVERED = "delivered"
    STATUS_RESPONDED = "responded"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_RESPONDED, "Responded"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELED, "Canceled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cos_prompt_schedules",
    )

    # What entity this prompt is about
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the source entity",
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the source entity",
    )
    source_entity = GenericForeignKey("content_type", "object_id")

    # Timing
    timing = models.CharField(
        max_length=4,
        choices=TIMING_CHOICES,
        help_text="Whether this fires before or after the activity",
    )
    scheduled_for = models.DateTimeField(
        db_index=True,
        help_text="When to deliver this prompt",
    )
    lead_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Minutes before activity start (for pre-activity prompts)",
    )

    # Content
    activity_type = models.CharField(
        max_length=50,
        help_text="Type of activity (workout, meeting, bible_study, etc.)",
    )
    prompt_text = models.TextField(
        help_text="The prompt message to deliver",
    )

    # Status
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    # Response tracking
    response_positive = models.BooleanField(
        null=True,
        blank=True,
        help_text="True = Yes/positive, False = No/negative, None = no response",
    )
    response_text = models.TextField(
        blank=True,
        help_text="Optional free-text response from the user",
    )

    class Meta:
        ordering = ["scheduled_for"]
        indexes = [
            models.Index(
                fields=["user", "status", "scheduled_for"],
                name="cos_prompt_user_status_sched",
            ),
            models.Index(
                fields=["status", "scheduled_for"],
                name="cos_prompt_status_sched",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_timing_display()} prompt for user {self.user_id} "
            f"({self.activity_type}) at {self.scheduled_for}"
        )

    def mark_delivered(self):
        self.status = self.STATUS_DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at", "updated_at"])

    def mark_responded(self, positive: bool, text: str = ""):
        self.status = self.STATUS_RESPONDED
        self.responded_at = timezone.now()
        self.response_positive = positive
        self.response_text = text
        self.save(
            update_fields=[
                "status",
                "responded_at",
                "response_positive",
                "response_text",
                "updated_at",
            ]
        )

    def mark_expired(self):
        self.status = self.STATUS_EXPIRED
        self.save(update_fields=["status", "updated_at"])

    def cancel(self):
        self.status = self.STATUS_CANCELED
        self.save(update_fields=["status", "updated_at"])


# ──────────────────────────────────────────────────────────
# CosGoalSuggestion — Goal suggestion throttling + decline tracking
# ──────────────────────────────────────────────────────────


class CosGoalSuggestion(TimeStampedModel):
    """
    Tracks goal suggestions made by the CoS, with throttling and opt-out.

    Policy:
    - Max ~1 suggestion per month per theme
    - Never auto-create goals
    - If declined 3 times for the same theme → ask "stop suggesting this?"
    - If user says yes to stop → theme is opted out
    """

    STATUS_SUGGESTED = "suggested"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_OPTED_OUT = "opted_out"
    STATUS_CHOICES = [
        (STATUS_SUGGESTED, "Suggested"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_OPTED_OUT, "Opted Out"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cos_goal_suggestions",
    )
    theme = models.CharField(
        max_length=100,
        help_text="Goal theme/category (e.g. 'fitness_consistency', 'sleep_improvement')",
    )
    suggestion_text = models.TextField(
        help_text="The suggested goal description",
    )
    evidence_summary = models.TextField(
        blank=True,
        help_text="Evidence from patterns/reflections supporting this suggestion",
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_SUGGESTED,
    )
    declined_count = models.PositiveIntegerField(
        default=0,
        help_text="How many times this theme has been declined (cumulative)",
    )
    opted_out = models.BooleanField(
        default=False,
        help_text="User opted out of suggestions for this theme",
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "theme", "created_at"],
                name="cos_goal_user_theme_date",
            ),
            models.Index(
                fields=["user", "opted_out"],
                name="cos_goal_user_optout",
            ),
        ]

    def __str__(self):
        return (
            f"Goal suggestion for user {self.user_id}: "
            f"{self.theme} ({self.status})"
        )

    @classmethod
    def get_theme_decline_count(cls, user, theme: str) -> int:
        """Get total decline count for a theme across all suggestions."""
        return (
            cls.objects.filter(
                user=user,
                theme=theme,
                status=cls.STATUS_DECLINED,
            ).count()
        )

    @classmethod
    def is_theme_opted_out(cls, user, theme: str) -> bool:
        """Check if user has opted out of a theme."""
        return cls.objects.filter(
            user=user,
            theme=theme,
            opted_out=True,
        ).exists()

    @classmethod
    def last_suggestion_date(cls, user, theme: str):
        """Return the date of the last suggestion for this theme, or None."""
        latest = (
            cls.objects.filter(user=user, theme=theme)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        return latest.date() if latest else None


# ──────────────────────────────────────────────────────────
# CosAutoShiftLog — Audit trail for automatic event shifts
# ──────────────────────────────────────────────────────────


class CosAutoShiftLog(TimeStampedModel):
    """
    Audit log for events automatically shifted by the CoS.

    Every auto-shift is logged for transparency and debugging.
    The user can review what the CoS moved and why.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cos_auto_shift_logs",
    )

    # What was shifted
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the shifted entity",
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the shifted entity",
    )
    shifted_entity = GenericForeignKey("content_type", "object_id")

    # Shift details
    original_start = models.DateTimeField(
        help_text="Original start time before shift",
    )
    original_end = models.DateTimeField(
        help_text="Original end time before shift",
    )
    new_start = models.DateTimeField(
        help_text="New start time after shift",
    )
    new_end = models.DateTimeField(
        help_text="New end time after shift",
    )

    # Why it was shifted
    reason = models.TextField(
        help_text="Human-readable reason for the shift",
    )
    shift_type = models.CharField(
        max_length=30,
        choices=[
            ("conflict_avoidance", "Conflict Avoidance"),
            ("priority_rebalance", "Priority Rebalance"),
            ("time_optimization", "Time Optimization"),
        ],
        help_text="Category of shift",
    )
    priority_level = models.CharField(
        max_length=10,
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
        ],
        help_text="Priority of the shifted item",
    )

    # Whether user was asked / confirmed
    user_confirmed = models.BooleanField(
        default=False,
        help_text="Whether user explicitly approved this shift",
    )
    auto_shifted = models.BooleanField(
        default=True,
        help_text="True if CoS shifted automatically (low priority only)",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "created_at"],
                name="cos_shift_user_date",
            ),
        ]

    def __str__(self):
        return (
            f"Auto-shift for user {self.user_id}: "
            f"{self.original_start} → {self.new_start} ({self.shift_type})"
        )
