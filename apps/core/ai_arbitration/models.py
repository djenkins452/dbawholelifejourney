"""
UAL — ArbitrationDecisionLog model.

Logs every arbitration decision for future refinement.
Not exposed in UI — purely for backend analysis.
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
