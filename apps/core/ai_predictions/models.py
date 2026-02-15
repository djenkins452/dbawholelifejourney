"""
PRIE — Prediction model for storing trajectory projections.
"""

import hashlib

from django.conf import settings
from django.db import models


class Prediction(models.Model):
    """
    Stores a single trajectory prediction for a user.

    Each prediction is a forward projection derived from real historical
    data using deterministic math (linear regression). Never guessed,
    always explainable.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("superseded", "Superseded"),  # replaced by newer prediction
        ("expired", "Expired"),  # past predicted_date
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prie_predictions",
    )
    prediction_type = models.CharField(max_length=120)  # e.g. weight_30d
    module = models.CharField(max_length=100)  # e.g. health, goals
    predicted_value = models.FloatField(null=True, blank=True)
    predicted_date = models.DateTimeField()
    confidence_score = models.FloatField()  # 0.0-1.0
    explanation = models.TextField()
    evidence = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active"
    )
    dedupe_key = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_ai_prediction"
        indexes = [
            models.Index(fields=["user", "prediction_type"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"{self.prediction_type} → {self.predicted_value} ({self.confidence_score:.0%})"


def build_prediction_dedupe_key(user_id, prediction_type, predicted_date_str):
    """Build a unique dedupe key for prediction upsert logic."""
    raw = f"{user_id}|{prediction_type}|{predicted_date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]
