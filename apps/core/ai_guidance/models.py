"""
PGE -- Proactive Guidance Model.

Stores proactive guidance items that are surfaced to users.
Each item represents actionable intelligence derived from
SAE state, PIE insights, or PRIE predictions.
"""

import hashlib

from django.conf import settings
from django.db import models


def _get_now():
    """Get current time using HTIE system clock (with fallback)."""
    try:
        from apps.core.time.system_clock import get_current_time

        return get_current_time()
    except ImportError:
        from django.utils import timezone

        return timezone.now()


class GuidanceItem(models.Model):
    """
    A single proactive guidance item surfaced to the user.

    Guidance is always evidence-based — it references real insights
    or predictions and includes a confidence level if predictive.
    Guidance never invents information.
    """

    PRIORITY_CHOICES = [
        (1, "Critical"),
        (2, "High"),
        (3, "Medium"),
        (4, "Low"),
        (5, "Info"),
    ]

    SOURCE_CHOICES = [
        ("pie_insight", "PIE Insight"),
        ("prie_prediction", "PRIE Prediction"),
        ("sae_state", "SAE State"),
        ("composite", "Composite (multiple sources)"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guidance_items",
    )
    title = models.CharField(
        max_length=255,
        help_text="Short guidance headline",
    )
    message = models.TextField(
        help_text="Detailed guidance message with context",
    )
    priority = models.IntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
        help_text="1=Critical, 5=Info",
    )
    guidance_type = models.CharField(
        max_length=100,
        help_text="Rule that generated this (e.g., 'goal_risk', 'health_trend')",
    )
    source = models.CharField(
        max_length=50,
        choices=SOURCE_CHOICES,
        default="composite",
        help_text="Which engine provided the primary data",
    )
    module = models.CharField(
        max_length=50,
        blank=True,
        help_text="Domain module (health, goals, habits, etc.)",
    )

    # Evidence and confidence
    confidence_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Confidence score if derived from prediction (0.0-1.0)",
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured evidence supporting this guidance",
    )

    # Lifecycle
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this guidance is currently active",
    )
    is_read = models.BooleanField(
        default=False,
        help_text="Whether the user has seen this guidance",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this guidance becomes irrelevant",
    )

    # Lifecycle tracking
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user acknowledged this guidance",
    )
    dismissed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user dismissed this guidance",
    )
    snoozed_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Guidance is hidden until this time",
    )
    acted_upon_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user took action on this guidance",
    )
    action_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="What action the user took (e.g., 'navigated', 'updated_goal')",
    )
    feedback = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional user feedback on the guidance quality",
    )

    # Deduplication
    dedupe_key = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Prevents duplicate guidance for same situation",
    )

    # Metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured data for rendering",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_guidance_item"
        ordering = ["priority", "-created_at"]
        verbose_name = "Guidance Item"
        verbose_name_plural = "Guidance Items"
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "priority"]),
            models.Index(fields=["user", "is_active", "priority"]),
            models.Index(fields=["dedupe_key"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["snoozed_until"]),
        ]

    def __str__(self):
        return f"[P{self.priority}] {self.title}"

    # ------------------------------------------------------------------
    # Lifecycle status properties
    # ------------------------------------------------------------------

    @property
    def is_acknowledged(self):
        """Whether the user has acknowledged this guidance."""
        return self.acknowledged_at is not None

    @property
    def is_dismissed(self):
        """Whether the user has dismissed this guidance."""
        return self.dismissed_at is not None

    @property
    def is_snoozed(self):
        """Whether this guidance is currently snoozed."""
        if not self.snoozed_until:
            return False
        try:
            from apps.core.time.system_clock import get_current_time

            return self.snoozed_until > get_current_time()
        except ImportError:
            from django.utils import timezone

            return self.snoozed_until > timezone.now()

    @property
    def is_acted_upon(self):
        """Whether the user has taken action on this guidance."""
        return self.acted_upon_at is not None

    @property
    def is_active_guidance(self):
        """Whether this guidance should be shown to the user."""
        return self.is_active and not self.is_dismissed and not self.is_snoozed

    # ------------------------------------------------------------------
    # Lifecycle action methods
    # ------------------------------------------------------------------

    def mark_read(self):
        """Mark this guidance item as read."""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read", "updated_at"])

    def acknowledge(self):
        """Mark this guidance item as acknowledged by the user."""
        if not self.acknowledged_at:
            self.acknowledged_at = _get_now()
            self.is_read = True
            self.save(update_fields=["acknowledged_at", "is_read", "updated_at"])

    def dismiss(self):
        """Dismiss this guidance item. Sets dismissed_at and deactivates."""
        if not self.dismissed_at:
            self.dismissed_at = _get_now()
            self.is_active = False
            self.save(
                update_fields=["dismissed_at", "is_active", "updated_at"]
            )

    def snooze(self, until):
        """
        Snooze this guidance item until a specific time.

        Args:
            until: datetime — when the guidance should reappear.
        """
        self.snoozed_until = until
        self.save(update_fields=["snoozed_until", "updated_at"])

    def mark_acted_upon(self, action_type=None):
        """
        Mark that the user took action on this guidance.

        Args:
            action_type: Optional string describing the action taken.
        """
        if not self.acted_upon_at:
            self.acted_upon_at = _get_now()
            if action_type:
                self.action_type = action_type
            self.is_read = True
            update_fields = [
                "acted_upon_at", "is_read", "updated_at",
            ]
            if action_type:
                update_fields.append("action_type")
            self.save(update_fields=update_fields)

    def set_feedback(self, feedback_text):
        """Store user feedback on this guidance item."""
        self.feedback = feedback_text[:255]
        self.save(update_fields=["feedback", "updated_at"])

    def deactivate(self):
        """Deactivate this guidance item."""
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])


def build_guidance_dedupe_key(user_id, guidance_type, *extra_parts):
    """
    Build a unique dedupe key for guidance deduplication.

    Same guidance_type + context should not produce duplicates.
    """
    parts = [str(user_id), guidance_type] + [str(p) for p in extra_parts]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
