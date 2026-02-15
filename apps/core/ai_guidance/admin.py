"""
PGE -- Admin configuration.

Read-only admin for inspecting proactive guidance items.
"""

from django.contrib import admin

from apps.core.ai_guidance.models import GuidanceItem


@admin.register(GuidanceItem)
class GuidanceItemAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "priority",
        "guidance_type",
        "source",
        "module",
        "is_active",
        "is_read",
        "acknowledged_at",
        "dismissed_at",
        "snoozed_until",
        "acted_upon_at",
        "confidence_score",
        "created_at",
    ]
    list_filter = [
        "priority",
        "source",
        "module",
        "is_active",
        "is_read",
        "guidance_type",
    ]
    search_fields = ["title", "message", "user__email"]
    readonly_fields = [
        "user",
        "title",
        "message",
        "priority",
        "guidance_type",
        "source",
        "module",
        "confidence_score",
        "evidence",
        "is_active",
        "is_read",
        "expires_at",
        "acknowledged_at",
        "dismissed_at",
        "snoozed_until",
        "acted_upon_at",
        "action_type",
        "feedback",
        "dedupe_key",
        "metadata",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
