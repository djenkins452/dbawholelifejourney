"""
Phase 4 CoS — Feedback Loop Models.

Closes the intelligence feedback loops:
- PredictionOutcome: validates predictions against actual outcomes
- InsightEngagement: tracks user interaction with insights
- BriefingEngagement: tracks briefing/report read behavior
- InterventionEffectiveness: tracks whether interventions resolved drift

All learning is transparent, per-user, and stored for auditability.
"""

from django.conf import settings
from django.db import models


class PredictionOutcome(models.Model):
    """
    Tracks actual outcomes for PRIE predictions.

    When a prediction's predicted_date arrives, the validator
    compares predicted_value against actual_value and records accuracy.
    """

    prediction = models.OneToOneField(
        "core.Prediction",
        on_delete=models.CASCADE,
        related_name="outcome",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prediction_outcomes",
    )
    actual_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Actual observed value at predicted_date.",
    )
    error_abs = models.FloatField(
        default=0.0,
        help_text="Absolute error: |predicted - actual|",
    )
    error_pct = models.FloatField(
        default=0.0,
        help_text="Percentage error: |predicted - actual| / |actual| * 100",
    )
    accuracy_score = models.FloatField(
        default=0.0,
        help_text="Accuracy 0-1 (1 = perfect). Based on inverse of error_pct.",
    )
    validated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_prediction_outcome"
        ordering = ["-validated_at"]
        indexes = [
            models.Index(fields=["user", "validated_at"]),
        ]

    def __str__(self):
        return (
            f"Outcome for prediction {self.prediction_id}: "
            f"predicted={self.prediction.predicted_value}, "
            f"actual={self.actual_value}, accuracy={self.accuracy_score:.2f}"
        )


class PredictionAccuracyProfile(models.Model):
    """
    Per-user, per-prediction_type aggregate accuracy profile.

    Updated incrementally when outcomes are recorded.
    Used to dynamically adjust confidence in future predictions.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prediction_accuracy_profiles",
    )
    prediction_type = models.CharField(max_length=120)
    total_validated = models.IntegerField(default=0)
    total_accurate = models.IntegerField(
        default=0,
        help_text="Count where accuracy_score >= 0.7",
    )
    avg_accuracy = models.FloatField(default=0.5)
    avg_error_pct = models.FloatField(default=0.0)
    confidence_adjustment = models.FloatField(
        default=0.0,
        help_text="Adjustment factor (-0.3 to +0.2) applied to future predictions.",
    )
    last_validated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_prediction_accuracy_profile"
        unique_together = ["user", "prediction_type"]
        indexes = [
            models.Index(fields=["user", "prediction_type"]),
        ]

    def __str__(self):
        return (
            f"Accuracy for {self.prediction_type} (user {self.user_id}): "
            f"{self.avg_accuracy:.2f} over {self.total_validated} predictions"
        )


class InsightEngagement(models.Model):
    """
    Tracks user engagement with PIE insights.

    Records view, act, dismiss events. Fed into PIE rule
    weight adjustments to surface more relevant insights.
    """

    EVENT_CHOICES = [
        ("viewed", "Viewed"),
        ("acted", "Acted Upon"),
        ("dismissed", "Dismissed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="insight_engagements",
    )
    insight = models.ForeignKey(
        "core.Insight",
        on_delete=models.CASCADE,
        related_name="engagements",
    )
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    event_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_insight_engagement"
        ordering = ["-event_at"]
        indexes = [
            models.Index(fields=["user", "event_at"]),
            models.Index(fields=["insight", "event_type"]),
        ]

    def __str__(self):
        return f"{self.event_type} insight {self.insight_id} by user {self.user_id}"


class InsightEngagementProfile(models.Model):
    """
    Per-user aggregate insight engagement profile.

    Tracks overall engagement patterns. Used by PIE ranker
    to adjust insight priority and severity weighting.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="insight_engagement_profile",
    )
    total_insights_shown = models.IntegerField(default=0)
    total_viewed = models.IntegerField(default=0)
    total_acted = models.IntegerField(default=0)
    total_dismissed = models.IntegerField(default=0)
    engagement_score = models.FloatField(
        default=0.5,
        help_text="Composite engagement score 0-1.",
    )
    preferred_severity = models.CharField(
        max_length=20,
        blank=True,
        help_text="Severity level user engages with most (info/positive/warning/critical).",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_insight_engagement_profile"

    def __str__(self):
        return f"Insight engagement for user {self.user_id} (score={self.engagement_score:.2f})"


class BriefingEngagement(models.Model):
    """
    Tracks engagement with daily briefings and weekly reports.

    Records open events and time spent. Used to adjust
    briefing length and tone dynamically.
    """

    CONTENT_TYPE_CHOICES = [
        ("daily_briefing", "Daily Briefing"),
        ("weekly_report", "Weekly Report"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="briefing_engagements",
    )
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_id = models.PositiveIntegerField(
        help_text="PK of DailyBriefing or WeeklyIntelligenceReport.",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    time_spent_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Approximate seconds spent viewing.",
    )
    scrolled_to_end = models.BooleanField(
        default=False,
        help_text="Whether user scrolled through entire content.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_briefing_engagement"
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["user", "content_type", "opened_at"]),
        ]

    def __str__(self):
        return f"{self.content_type} {self.content_id} opened by user {self.user_id}"


class BriefingEngagementProfile(models.Model):
    """
    Per-user aggregate briefing engagement profile.

    Used to adjust briefing verbosity and tone:
    - Low engagement → shorter, punchier briefings
    - High engagement → richer, more detailed briefings
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="briefing_engagement_profile",
    )
    total_briefings_generated = models.IntegerField(default=0)
    total_briefings_opened = models.IntegerField(default=0)
    total_reports_generated = models.IntegerField(default=0)
    total_reports_opened = models.IntegerField(default=0)
    avg_time_spent_seconds = models.FloatField(default=0.0)
    open_rate = models.FloatField(
        default=0.0,
        help_text="Briefings opened / briefings generated.",
    )
    preferred_length = models.CharField(
        max_length=10,
        default="standard",
        help_text="concise / standard / detailed — derived from engagement.",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_briefing_engagement_profile"

    def __str__(self):
        return f"Briefing engagement for user {self.user_id} (open_rate={self.open_rate:.2f})"


class InterventionEffectivenessProfile(models.Model):
    """
    Per-user aggregate intervention effectiveness profile.

    Tracks whether interventions actually resolve drift.
    Used to calibrate escalation speed:
    - Responsive user → slower escalation
    - Non-responsive user → faster escalation
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="intervention_effectiveness_profile",
    )
    total_interventions = models.IntegerField(default=0)
    total_accepted = models.IntegerField(default=0)
    total_dismissed = models.IntegerField(default=0)
    total_drift_resolved = models.IntegerField(
        default=0,
        help_text="Interventions where drift decreased within 24h.",
    )
    effectiveness_score = models.FloatField(
        default=0.5,
        help_text="0-1 score based on acceptance + drift resolution rate.",
    )
    avg_response_time_seconds = models.FloatField(default=0.0)
    escalation_speed_modifier = models.FloatField(
        default=0.0,
        help_text="Modifier for escalation timing. Negative = slower, positive = faster.",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_intervention_effectiveness_profile"

    def __str__(self):
        return (
            f"Intervention effectiveness for user {self.user_id} "
            f"(score={self.effectiveness_score:.2f})"
        )
