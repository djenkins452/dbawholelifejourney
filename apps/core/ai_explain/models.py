"""
E3 — Models.

ExplainRecord: Stores evidence and explainability metadata for intelligence outputs.
Each record links to a source engine object (GuidanceItem, DailyBriefing, etc.)
and provides human-readable explanations with structured evidence.
"""

from django.conf import settings
from django.db import models


class ExplainRecord(models.Model):
    """
    Evidence and explainability metadata for an intelligence output.

    Answers: "Why is the system saying this?" and "What data is it based on?"
    Links to one source object from PIE, PRIE, PGE, DBE, or WIRE.
    """

    ENGINE_CHOICES = [
        ("PIE", "Proactive Insight Engine"),
        ("PRIE", "Predictive Intelligence Engine"),
        ("PGE", "Proactive Guidance Engine"),
        ("DBE", "Daily Briefing Engine"),
        ("WIRE", "Weekly Intelligence Report Engine"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="explain_records",
    )
    source_engine = models.CharField(
        max_length=10,
        choices=ENGINE_CHOICES,
        help_text="Which engine produced the intelligence output.",
    )
    source_object_type = models.CharField(
        max_length=100,
        help_text="Model name of source object (e.g., GuidanceItem, DailyBriefing).",
    )
    source_object_id = models.IntegerField(
        help_text="PK of the source object.",
    )
    title = models.CharField(
        max_length=255,
        help_text="Short title of the intelligence output.",
    )
    explanation = models.TextField(
        help_text="Human-readable explanation of why this was generated.",
    )
    confidence_explanation = models.TextField(
        null=True,
        blank=True,
        help_text="Why the confidence score is what it is.",
    )
    evidence = models.JSONField(
        default=list,
        help_text="List of evidence objects with type, id, date, summary, url.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_explain_record"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "source_engine"],
                name="idx_explain_user_engine",
            ),
            models.Index(
                fields=["user", "source_object_type", "source_object_id"],
                name="idx_explain_user_obj",
            ),
        ]
        verbose_name = "Explain Record"
        verbose_name_plural = "Explain Records"

    def __str__(self):
        return (
            f"E3: {self.source_engine}/{self.source_object_type}"
            f"#{self.source_object_id} for user {self.user_id}"
        )
