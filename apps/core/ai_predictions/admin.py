"""
PRIE — Admin registration for Prediction model.
"""

from django.contrib import admin

from apps.core.ai_predictions.models import Prediction


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "prediction_type",
        "module",
        "predicted_value",
        "confidence_score",
        "status",
        "predicted_date",
        "created_at",
    ]
    list_filter = ["module", "status", "prediction_type"]
    search_fields = ["user__email", "prediction_type", "explanation"]
    readonly_fields = [
        "user",
        "prediction_type",
        "module",
        "predicted_value",
        "predicted_date",
        "confidence_score",
        "explanation",
        "evidence",
        "dedupe_key",
        "status",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False  # Predictions are system-generated only
