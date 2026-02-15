"""
DBE — Admin registration.

Daily briefings are system-generated and read-only in admin.
"""

from django.contrib import admin

from apps.core.ai_briefing.models import DailyBriefing


@admin.register(DailyBriefing)
class DailyBriefingAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "briefing_date",
        "short_summary",
        "created_at",
    ]
    list_filter = ["briefing_date"]
    search_fields = ["user__email", "summary"]
    readonly_fields = [
        "user",
        "briefing_date",
        "summary",
        "state_snapshot",
        "guidance_snapshot",
        "insight_snapshot",
        "prediction_snapshot",
        "created_at",
    ]
    ordering = ["-briefing_date", "-created_at"]

    def short_summary(self, obj):
        if obj.summary and len(obj.summary) > 80:
            return obj.summary[:80] + "…"
        return obj.summary or ""

    short_summary.short_description = "Summary"

    def has_add_permission(self, request):
        return False  # System-generated only

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
