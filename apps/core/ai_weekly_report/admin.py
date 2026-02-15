"""
WIRE — Admin configuration.

Read-only admin for monitoring weekly intelligence reports.
"""

from django.contrib import admin

from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport


@admin.register(WeeklyIntelligenceReport)
class WeeklyIntelligenceReportAdmin(admin.ModelAdmin):
    """Read-only admin for weekly intelligence reports."""

    list_display = [
        "user",
        "week_start_date",
        "week_end_date",
        "summary_preview",
        "created_at",
    ]
    list_filter = ["week_start_date"]
    search_fields = ["user__email", "summary"]
    readonly_fields = [
        "user",
        "week_start_date",
        "week_end_date",
        "summary",
        "state_delta_snapshot",
        "insight_snapshot",
        "prediction_snapshot",
        "guidance_snapshot",
        "learning_snapshot",
        "created_at",
    ]

    def summary_preview(self, obj):
        return obj.summary[:80] + "..." if len(obj.summary) > 80 else obj.summary
    summary_preview.short_description = "Summary"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
