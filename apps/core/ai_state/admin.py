"""
SAE — Admin Registration.

Read-only display for inspection and debugging.
Manual editing is not allowed.
"""

from django.contrib import admin

from apps.core.ai_state.models import UserState


@admin.register(UserState)
class UserStateAdmin(admin.ModelAdmin):
    list_display = ("user", "module_count", "last_updated", "created_at")
    list_filter = ("last_updated",)
    search_fields = ("user__email",)
    readonly_fields = (
        "user",
        "state_data",
        "last_updated",
        "created_at",
    )

    def module_count(self, obj):
        if obj.state_data:
            return len(obj.state_data)
        return 0

    module_count.short_description = "Modules"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
