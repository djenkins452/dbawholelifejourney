"""
GLOE — Admin registration.

Read-only views for learning profiles and events.
"""

from django.contrib import admin

from apps.core.ai_guidance_learning.learning_models import (
    GuidanceLearningEvent,
    GuidanceLearningProfile,
)


@admin.register(GuidanceLearningProfile)
class GuidanceLearningProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "total_guidance_seen",
        "total_guidance_acknowledged",
        "total_guidance_dismissed",
        "total_guidance_acted",
        "responsiveness_score",
        "avg_response_time_seconds",
        "last_updated",
    ]
    list_filter = []
    search_fields = ["user__email"]
    readonly_fields = [
        "user",
        "total_guidance_seen",
        "total_guidance_acknowledged",
        "total_guidance_dismissed",
        "total_guidance_acted",
        "avg_response_time_seconds",
        "responsiveness_score",
        "last_updated",
    ]
    ordering = ["-last_updated"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GuidanceLearningEvent)
class GuidanceLearningEventAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "guidance_item",
        "event_type",
        "response_time_seconds",
        "event_timestamp",
    ]
    list_filter = ["event_type"]
    search_fields = ["user__email"]
    readonly_fields = [
        "user",
        "guidance_item",
        "event_type",
        "event_timestamp",
        "response_time_seconds",
    ]
    ordering = ["-event_timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
