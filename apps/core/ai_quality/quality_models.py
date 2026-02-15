"""
ICQG — Models for Intelligence Calibration & Quality Gate.

QualitySuppressionRecord: Tracks repeated guidance suppression.
QualityMetricAggregate: Weekly performance metrics per rule/domain.
"""

import hashlib

from django.conf import settings
from django.db import models


class QualitySuppressionRecord(models.Model):
    """
    Tracks repeated guidance suppression.

    When the same guidance signature appears within the suppression window
    (72 hours by default), it is suppressed unless severity has increased.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quality_suppressions",
    )
    signature_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 of guidance_type + key evidence IDs + title",
    )
    suppressed_until = models.DateTimeField(
        help_text="Do not show this guidance again until this time",
    )
    last_seen_at = models.DateTimeField(
        help_text="Last time this guidance signature was generated",
    )
    last_priority = models.IntegerField(
        default=3,
        help_text="Priority when last suppressed (1=Critical, 5=Info)",
    )
    count = models.IntegerField(
        default=1,
        help_text="Number of times this guidance signature has been seen",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_quality_suppression"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "signature_hash"],
                name="unique_user_suppression_signature",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "suppressed_until"],
                name="idx_suppression_user_until",
            ),
        ]
        verbose_name = "Quality Suppression Record"
        verbose_name_plural = "Quality Suppression Records"

    def __str__(self):
        return f"Suppression {self.signature_hash[:12]}... (user {self.user_id}, count={self.count})"

    @staticmethod
    def compute_signature(guidance_type, title, evidence_ids=None):
        """
        Compute a signature hash for a guidance candidate.

        Args:
            guidance_type: The rule type (e.g., 'goal_risk', 'health_trend').
            title: The guidance title.
            evidence_ids: Optional list/tuple of evidence IDs.

        Returns:
            SHA-256 hex digest string.
        """
        parts = [str(guidance_type), str(title)]
        if evidence_ids:
            parts.extend(str(eid) for eid in sorted(evidence_ids))
        raw = ":".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()


class QualityMetricAggregate(models.Model):
    """
    Weekly aggregated quality metrics per rule type and domain.

    Computed by the ICQG metrics aggregation job (weekly via ISE).
    """

    week_start = models.DateField(
        help_text="Monday of the metric week",
    )
    rule_type = models.CharField(
        max_length=120,
        help_text="Guidance type / rule that generated items",
    )
    domain = models.CharField(
        max_length=100,
        help_text="Module domain (health, goals, habits, etc.)",
    )
    delivered_count = models.IntegerField(default=0)
    acted_count = models.IntegerField(default=0)
    dismissed_count = models.IntegerField(default=0)
    snoozed_count = models.IntegerField(default=0)
    acknowledged_count = models.IntegerField(default=0)
    suppressed_count = models.IntegerField(default=0)
    avg_response_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Average time to user action in seconds",
    )
    usefulness_score = models.FloatField(
        default=0.5,
        help_text="Composite usefulness score 0.0-1.0",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_quality_metric_aggregate"
        constraints = [
            models.UniqueConstraint(
                fields=["week_start", "rule_type", "domain"],
                name="unique_quality_metric_week_rule_domain",
            ),
        ]
        indexes = [
            models.Index(
                fields=["week_start", "usefulness_score"],
                name="idx_qmetric_week_score",
            ),
        ]
        ordering = ["-week_start", "-usefulness_score"]
        verbose_name = "Quality Metric Aggregate"
        verbose_name_plural = "Quality Metric Aggregates"

    def __str__(self):
        return (
            f"{self.rule_type}/{self.domain} week={self.week_start} "
            f"score={self.usefulness_score:.2f}"
        )
