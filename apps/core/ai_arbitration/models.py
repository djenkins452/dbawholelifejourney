"""
UAL — Arbitration Models.

Models:
- ArbitrationDecisionLog: Records every UAL decision for refinement
- ScenarioHistory: Daily scenario tracking for pattern analysis
- WeightAdjustment: Adaptive weight tuning per scenario/signal
- DailyCapacityLog: Daily capacity state tracking
"""
import logging

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class ArbitrationDecisionLog(models.Model):
    """Records each UAL arbitration decision for refinement."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="arbitration_logs",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # Classification
    dominant_scenario = models.CharField(max_length=50)
    secondary_scenarios = models.JSONField(default=list, blank=True)
    fused_signals = models.JSONField(default=dict, blank=True)

    # Confidence (v2)
    confidence_level = models.CharField(
        max_length=20,
        default="MODERATE",
        help_text="LOW / MODERATE / HIGH based on confidence gap.",
    )

    # Capacity (v2)
    capacity_state = models.CharField(
        max_length=20,
        default="NORMAL",
        help_text="CRITICAL / LOW / NORMAL / HIGH_CAPACITY.",
    )
    capacity_score = models.FloatField(
        default=0.5,
        help_text="Capacity composite score 0-1.",
    )

    # Decision
    intervention_style = models.CharField(max_length=30)
    surfaced_items = models.JSONField(default=list, blank=True)
    suppressed_items = models.JSONField(default=list, blank=True)
    narrative = models.TextField(blank=True, default="")

    # Signal snapshot
    raw_signals = models.JSONField(default=dict, blank=True)
    scenario_scores = models.JSONField(default=dict, blank=True)

    # Feedback (nullable — populated later)
    user_response = models.CharField(max_length=255, null=True, blank=True)
    outcome_score = models.FloatField(null=True, blank=True)

    class Meta:
        app_label = "core"
        db_table = "core_arbitration_decision_log"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["dominant_scenario"]),
        ]

    def __str__(self):
        return (
            f"UAL {self.dominant_scenario} → {self.intervention_style} "
            f"({self.timestamp:%Y-%m-%d %H:%M})"
        )


class ScenarioHistory(models.Model):
    """
    Daily scenario tracking for pattern analysis.

    One record per user per day. Used by PatternAnalyzer
    to detect multi-day repetition patterns.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scenario_history",
    )
    date = models.DateField()
    dominant_scenario = models.CharField(max_length=50)
    intervention_style = models.CharField(max_length=30)
    capacity_state = models.CharField(
        max_length=20,
        default="NORMAL",
    )
    suppressed_count = models.IntegerField(default=0)
    surfaced_count = models.IntegerField(default=0)

    class Meta:
        app_label = "core"
        db_table = "core_scenario_history"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                name="unique_scenario_per_user_day",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-date"]),
            models.Index(fields=["dominant_scenario"]),
        ]

    def __str__(self):
        return f"{self.dominant_scenario} on {self.date}"


class WeightAdjustment(models.Model):
    """
    Adaptive weight tuning per scenario/signal pair.

    Tracks adjustments from baseline weights based on user
    compliance patterns. Adjustments are bounded ±0.10.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weight_adjustments",
    )
    scenario = models.CharField(max_length=50)
    signal = models.CharField(max_length=50)
    baseline_weight = models.FloatField(
        help_text="Original weight from SCENARIO_WEIGHTS.",
    )
    adjustment_delta = models.FloatField(
        default=0.0,
        help_text="Current offset from baseline. Clamped ±0.10.",
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_weight_adjustment"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "scenario", "signal"],
                name="unique_weight_per_user_scenario_signal",
            ),
        ]

    @property
    def current_weight(self):
        return self.baseline_weight + self.adjustment_delta

    def __str__(self):
        return (
            f"{self.scenario}/{self.signal}: "
            f"{self.baseline_weight:+.2f} → {self.current_weight:.2f} "
            f"(delta {self.adjustment_delta:+.3f})"
        )


class DailyCapacityLog(models.Model):
    """
    Daily capacity state for trend tracking.

    Logged once per day during arbitration. Used by
    observability dashboard for capacity trend lines.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="capacity_logs",
    )
    date = models.DateField()
    capacity_score = models.FloatField(
        help_text="Composite capacity score 0-1.",
    )
    capacity_state = models.CharField(
        max_length=20,
        help_text="CRITICAL / LOW / NORMAL / HIGH_CAPACITY.",
    )

    # Component scores for debugging
    sleep_deficit = models.FloatField(default=0.0)
    mood_decline = models.FloatField(default=0.0)
    emotional_load = models.FloatField(default=0.0)
    schedule_overload = models.FloatField(default=0.0)
    open_loop_count = models.FloatField(default=0.0)

    class Meta:
        app_label = "core"
        db_table = "core_daily_capacity_log"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                name="unique_capacity_per_user_day",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-date"]),
        ]

    def __str__(self):
        return f"Capacity {self.capacity_state} ({self.capacity_score:.2f}) on {self.date}"
