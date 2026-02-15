"""DNE — Admin configuration for DeliveredNotification."""

from django.contrib import admin

from apps.core.ai_delivery.models import DeliveredNotification


@admin.register(DeliveredNotification)
class DeliveredNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "user", "source_engine", "channel", "status", "title", "delivered_at",
    )
    list_filter = ("source_engine", "channel", "status")
    search_fields = ("title", "message", "user__email")
    readonly_fields = (
        "user", "source_engine", "source_object_type", "source_object_id",
        "channel", "title", "message", "action_url", "delivered_at",
        "status", "skip_reason", "dedupe_hash", "metadata",
    )
    ordering = ("-delivered_at",)
    date_hierarchy = "delivered_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
