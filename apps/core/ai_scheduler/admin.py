"""
ISE — Admin configuration.

Read-only admin interface for monitoring scheduler health.
"""

from django.contrib import admin

from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask


@admin.register(ScheduledIntelligenceTask)
class ScheduledIntelligenceTaskAdmin(admin.ModelAdmin):
    """Read-only admin for scheduled intelligence tasks."""

    list_display = [
        "task_name",
        "is_active",
        "last_status",
        "last_run_at",
        "next_run_at",
        "run_interval_display",
        "run_count",
    ]
    list_filter = ["is_active", "last_status"]
    search_fields = ["task_name", "description"]
    readonly_fields = [
        "task_name",
        "description",
        "last_run_at",
        "next_run_at",
        "run_interval_seconds",
        "last_status",
        "last_error",
        "run_count",
        "created_at",
        "updated_at",
    ]

    def run_interval_display(self, obj):
        hours = obj.run_interval_seconds / 3600
        if hours >= 24:
            return f"{hours / 24:.0f}d"
        return f"{hours:.0f}h"
    run_interval_display.short_description = "Interval"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        # Allow toggling is_active only
        return True

    def get_readonly_fields(self, request, obj=None):
        # Allow is_active to be toggled
        return self.readonly_fields
