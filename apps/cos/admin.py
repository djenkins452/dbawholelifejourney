from django.contrib import admin

from apps.cos.models import (
    CosAutoShiftLog,
    CosGoalSuggestion,
    CosPromptSchedule,
    CosReflection,
)


@admin.register(CosReflection)
class CosReflectionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "activity_type",
        "activity_date",
        "sentiment",
        "created_at",
    ]
    list_filter = ["activity_type", "sentiment", "activity_date"]
    search_fields = ["text", "user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CosPromptSchedule)
class CosPromptScheduleAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "activity_type",
        "timing",
        "status",
        "scheduled_for",
    ]
    list_filter = ["timing", "status", "activity_type"]
    search_fields = ["prompt_text", "user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CosGoalSuggestion)
class CosGoalSuggestionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "theme",
        "status",
        "declined_count",
        "opted_out",
        "created_at",
    ]
    list_filter = ["status", "opted_out", "theme"]
    search_fields = ["suggestion_text", "user__email", "theme"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CosAutoShiftLog)
class CosAutoShiftLogAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "shift_type",
        "priority_level",
        "auto_shifted",
        "user_confirmed",
        "created_at",
    ]
    list_filter = ["shift_type", "priority_level", "auto_shifted"]
    search_fields = ["reason", "user__email"]
    readonly_fields = ["created_at", "updated_at"]
