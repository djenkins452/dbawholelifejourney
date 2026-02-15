"""
E3 — Admin.

Read-only admin for ExplainRecord model.
"""

from django.contrib import admin

from apps.core.ai_explain.models import ExplainRecord


@admin.register(ExplainRecord)
class ExplainRecordAdmin(admin.ModelAdmin):
    """Read-only admin for ExplainRecord."""

    list_display = [
        "id",
        "user",
        "source_engine",
        "source_object_type",
        "source_object_id",
        "title",
        "created_at",
    ]
    list_filter = ["source_engine", "source_object_type"]
    search_fields = ["title", "explanation"]
    readonly_fields = [
        "user",
        "source_engine",
        "source_object_type",
        "source_object_id",
        "title",
        "explanation",
        "confidence_explanation",
        "evidence",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
