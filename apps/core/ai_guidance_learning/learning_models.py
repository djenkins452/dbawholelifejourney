"""
GLOE — Learning Models.

GuidanceLearningProfile: Per-user aggregate responsiveness metrics.
GuidanceLearningEvent: Individual lifecycle event records.
"""

from django.conf import settings
from django.db import models


class GuidanceLearningProfile(models.Model):
    """
    Per-user aggregate learning profile tracking guidance responsiveness.

    Updated incrementally when lifecycle events occur.
    Used by PGE ranker and DBE to adjust guidance scoring.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guidance_learning_profile",
    )
    total_guidance_seen = models.IntegerField(
        default=0,
        help_text="Total guidance items shown to this user.",
    )
    total_guidance_acknowledged = models.IntegerField(
        default=0,
        help_text="Total guidance items acknowledged.",
    )
    total_guidance_dismissed = models.IntegerField(
        default=0,
        help_text="Total guidance items dismissed.",
    )
    total_guidance_acted = models.IntegerField(
        default=0,
        help_text="Total guidance items acted upon.",
    )
    avg_response_time_seconds = models.FloatField(
        default=0.0,
        help_text="Average seconds between guidance creation and user action.",
    )
    responsiveness_score = models.FloatField(
        default=0.5,
        help_text="Composite responsiveness score (0.0-1.0).",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_guidance_learning_profile"
        verbose_name = "Guidance Learning Profile"
        verbose_name_plural = "Guidance Learning Profiles"

    def __str__(self):
        return f"Learning profile for user {self.user_id} (score={self.responsiveness_score:.2f})"


class GuidanceLearningEvent(models.Model):
    """
    Individual guidance lifecycle event for learning.

    Records each acknowledge, dismiss, or acted event with timing data.
    """

    EVENT_TYPE_CHOICES = [
        ("acknowledged", "Acknowledged"),
        ("dismissed", "Dismissed"),
        ("acted", "Acted Upon"),
        ("ignored", "Ignored"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guidance_learning_events",
    )
    guidance_item = models.ForeignKey(
        "core.GuidanceItem",
        on_delete=models.CASCADE,
        related_name="learning_events",
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
    )
    event_timestamp = models.DateTimeField(auto_now_add=True)
    response_time_seconds = models.FloatField(
        default=0.0,
        help_text="Seconds between guidance creation and this event.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_guidance_learning_event"
        ordering = ["-event_timestamp"]
        verbose_name = "Guidance Learning Event"
        verbose_name_plural = "Guidance Learning Events"

    def __str__(self):
        return f"{self.event_type} by user {self.user_id} on guidance {self.guidance_item_id}"
