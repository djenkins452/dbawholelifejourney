"""
CDCE — Cross-Domain Correlation Model.

Stores discovered correlations between domains. Each correlation represents
a statistically significant relationship between two metrics across different
life domains (e.g., sleep duration correlates with next-day mood).
"""

import hashlib

from django.conf import settings
from django.db import models


class DomainCorrelation(models.Model):
    """
    A cross-domain correlation discovered by the CDCE.

    Example: "When sleep drops below 6.5h, mood is negative the next day 78% of the time."
    """

    STRENGTH_CHOICES = [
        ("strong", "Strong"),       # r >= 0.7 or 70%+ co-occurrence
        ("moderate", "Moderate"),   # 0.5 <= r < 0.7
        ("weak", "Weak"),           # 0.3 <= r < 0.5
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("superseded", "Superseded"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="domain_correlations",
    )
    # Domain pair (e.g., "health" + "journal")
    domain_a = models.CharField(max_length=50)
    domain_b = models.CharField(max_length=50)
    correlation_type = models.CharField(
        max_length=100,
        help_text="e.g., 'sleep_mood', 'exercise_energy', 'finance_stress'",
    )

    # Strength and direction
    strength = models.CharField(max_length=20, choices=STRENGTH_CHOICES)
    strength_score = models.FloatField(
        help_text="0.0 to 1.0 — statistical strength of the correlation",
    )
    direction = models.CharField(
        max_length=20,
        default="positive",
        help_text="'positive' (both increase) or 'inverse' (one increases, other decreases)",
    )

    # Human-readable narrative
    narrative = models.TextField(
        help_text="Natural language description for CoS to reference in conversation",
    )
    evidence_summary = models.TextField(
        help_text="Brief evidence explanation (e.g., '14 of 18 low-sleep days had negative mood')",
    )

    # Structured evidence
    evidence = models.JSONField(
        default=dict,
        help_text="Raw data points, dates, metric values supporting the correlation",
    )
    data_points = models.IntegerField(
        default=0,
        help_text="Number of data points used to compute the correlation",
    )

    # Lifecycle
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    dedupe_key = models.CharField(max_length=255, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_domain_correlation"
        ordering = ["-strength_score", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "correlation_type"]),
            models.Index(fields=["dedupe_key"]),
        ]

    def __str__(self):
        return f"[{self.strength}] {self.correlation_type}: {self.narrative[:60]}"


def build_correlation_dedupe_key(user_id, correlation_type, window_label):
    """Build a unique dedupe key to prevent duplicate correlations."""
    raw = f"{user_id}|{correlation_type}|{window_label}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
