"""
UAL — Admin configuration.

Read-only admin for ArbitrationDecisionLog.
"""
from django.contrib import admin

from apps.core.ai_arbitration.models import ArbitrationDecisionLog


@admin.register(ArbitrationDecisionLog)
class ArbitrationDecisionLogAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "timestamp",
        "dominant_scenario",
        "intervention_style",
        "outcome_score",
    ]
    list_filter = ["dominant_scenario", "intervention_style"]
    search_fields = ["user__email"]
    readonly_fields = [
        "user",
        "timestamp",
        "dominant_scenario",
        "secondary_scenarios",
        "fused_signals",
        "intervention_style",
        "surfaced_items",
        "suppressed_items",
        "narrative",
        "raw_signals",
        "scenario_scores",
        "user_response",
        "outcome_score",
    ]
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Allow editing only outcome_score and user_response
        return True

    def has_delete_permission(self, request, obj=None):
        return False
