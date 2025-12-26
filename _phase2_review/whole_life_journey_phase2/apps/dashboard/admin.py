"""
Dashboard Admin Configuration
"""

from django.contrib import admin

from .models import DailyEncouragement


@admin.register(DailyEncouragement)
class DailyEncouragementAdmin(admin.ModelAdmin):
    list_display = [
        "message_preview",
        "scripture_reference",
        "is_faith_specific",
        "is_active",
        "day_of_week",
        "month",
    ]
    list_filter = ["is_faith_specific", "is_active", "translation"]
    search_fields = ["message", "scripture_reference", "scripture_text"]
    list_editable = ["is_active"]

    def message_preview(self, obj):
        return obj.message[:60] + "..." if len(obj.message) > 60 else obj.message
    message_preview.short_description = "Message"
