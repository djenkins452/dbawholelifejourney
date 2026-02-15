"""
WIRE — Models.

WeeklyIntelligenceReport: Stores one intelligence report per user per week.
"""

from django.conf import settings
from django.db import models


class WeeklyIntelligenceReport(models.Model):
    """
    A weekly intelligence summary aggregating SAE, PIE, PRIE, PGE, and GLOE data.

    One report per user per week (unique on user + week_start_date).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weekly_intelligence_reports",
    )
    week_start_date = models.DateField(
        help_text="Monday of the report week.",
    )
    week_end_date = models.DateField(
        help_text="Sunday of the report week.",
    )
    summary = models.TextField(
        help_text="Natural language summary of the week's intelligence.",
    )
    state_delta_snapshot = models.JSONField(
        default=dict,
        help_text="State changes between week start and end.",
    )
    insight_snapshot = models.JSONField(
        default=dict,
        help_text="Key insights from the week.",
    )
    prediction_snapshot = models.JSONField(
        default=dict,
        help_text="Important predictions from the week.",
    )
    guidance_snapshot = models.JSONField(
        default=dict,
        help_text="Guidance items and lifecycle activity.",
    )
    learning_snapshot = models.JSONField(
        default=dict,
        help_text="GLOE learning profile snapshot for the week.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_weekly_intelligence_report"
        ordering = ["-week_start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "week_start_date"],
                name="unique_weekly_report_per_user",
            ),
        ]
        verbose_name = "Weekly Intelligence Report"
        verbose_name_plural = "Weekly Intelligence Reports"

    def __str__(self):
        return (
            f"Weekly Report for user {self.user_id}: "
            f"{self.week_start_date} — {self.week_end_date}"
        )
