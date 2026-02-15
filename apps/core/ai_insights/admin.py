"""
PIE Django Admin — Insight management.
"""

from django.contrib import admin

from apps.core.ai_insights.models import Insight


@admin.register(Insight)
class InsightAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "module",
        "insight_type",
        "severity",
        "confidence_score",
        "status",
        "created_at",
    ]
    list_filter = ["severity", "status", "module", "insight_type"]
    search_fields = ["user__email", "title", "insight_type", "message"]
    readonly_fields = ["dedupe_key", "created_at", "updated_at"]
    list_per_page = 50

    def has_add_permission(self, request):
        return False  # Insights are system-generated only
