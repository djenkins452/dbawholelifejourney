"""
UAL — Admin configuration.

Read-only admin for ArbitrationDecisionLog, v2 and v2.1 models.
"""
from django.contrib import admin

from apps.core.ai_arbitration.models import (
    ArbitrationDecisionLog,
    DailyCapacityLog,
    InterventionResponseLog,
    RecentNudgeMemory,
    ScenarioHistory,
    WeightAdjustment,
)


@admin.register(ArbitrationDecisionLog)
class ArbitrationDecisionLogAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "timestamp",
        "dominant_scenario",
        "confidence_level",
        "capacity_state",
        "intervention_style",
        "outcome_score",
    ]
    list_filter = [
        "dominant_scenario",
        "intervention_style",
        "confidence_level",
        "capacity_state",
    ]
    search_fields = ["user__email"]
    readonly_fields = [
        "user",
        "timestamp",
        "dominant_scenario",
        "secondary_scenarios",
        "fused_signals",
        "confidence_level",
        "capacity_state",
        "capacity_score",
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


@admin.register(ScenarioHistory)
class ScenarioHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "user", "date", "dominant_scenario", "intervention_style",
        "capacity_state", "surfaced_count", "suppressed_count",
    ]
    list_filter = ["dominant_scenario", "capacity_state"]
    search_fields = ["user__email"]
    ordering = ["-date"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WeightAdjustment)
class WeightAdjustmentAdmin(admin.ModelAdmin):
    list_display = [
        "user", "scenario", "signal", "baseline_weight",
        "adjustment_delta", "current_weight", "last_updated",
    ]
    list_filter = ["scenario"]
    search_fields = ["user__email"]
    ordering = ["scenario", "signal"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyCapacityLog)
class DailyCapacityLogAdmin(admin.ModelAdmin):
    list_display = [
        "user", "date", "capacity_state", "capacity_score",
    ]
    list_filter = ["capacity_state"]
    search_fields = ["user__email"]
    ordering = ["-date"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InterventionResponseLog)
class InterventionResponseLogAdmin(admin.ModelAdmin):
    list_display = [
        "user", "date", "scenario", "surfaced_count",
        "complied_count", "ignored_count", "overrode_count",
    ]
    list_filter = ["scenario"]
    search_fields = ["user__email"]
    ordering = ["-date"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecentNudgeMemory)
class RecentNudgeMemoryAdmin(admin.ModelAdmin):
    list_display = [
        "user", "surfaced_at", "scenario", "semantic_tag", "trace_id",
    ]
    list_filter = ["scenario"]
    search_fields = ["user__email", "semantic_tag"]
    ordering = ["-surfaced_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
