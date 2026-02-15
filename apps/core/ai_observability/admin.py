"""
IOCD — Admin registration (read-only).
"""

from django.contrib import admin

from apps.core.ai_observability.models import IntelligenceMetricsSnapshot


@admin.register(IntelligenceMetricsSnapshot)
class IntelligenceMetricsSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "snapshot_date",
        "guidance_total",
        "guidance_action_rate",
        "deliveries_success_rate",
        "avg_usefulness_score",
        "active_users_count",
    ]
    list_filter = ["snapshot_date"]
    readonly_fields = [
        "snapshot_date",
        "guidance_total",
        "guidance_acknowledged",
        "guidance_dismissed",
        "guidance_acted",
        "guidance_expired",
        "guidance_acceptance_rate",
        "guidance_action_rate",
        "guidance_avg_response_seconds",
        "predictions_total",
        "predictions_active",
        "predictions_expired",
        "predictions_avg_confidence",
        "deliveries_total",
        "deliveries_sent",
        "deliveries_skipped",
        "deliveries_failed",
        "deliveries_success_rate",
        "deliveries_by_channel",
        "active_users_count",
        "avg_responsiveness_score",
        "avg_usefulness_score",
        "total_suppressed",
        "persona_effectiveness_scores",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
