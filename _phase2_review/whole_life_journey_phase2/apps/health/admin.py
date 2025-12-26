"""
Health Admin Configuration
"""

from django.contrib import admin

from .models import FastingWindow, GlucoseEntry, HeartRateEntry, WeightEntry


@admin.register(WeightEntry)
class WeightEntryAdmin(admin.ModelAdmin):
    list_display = ["user", "value", "unit", "recorded_at", "status"]
    list_filter = ["unit", "status", "recorded_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "recorded_at"


@admin.register(FastingWindow)
class FastingWindowAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "fasting_type",
        "started_at",
        "ended_at",
        "duration_display",
        "status",
    ]
    list_filter = ["fasting_type", "status", "started_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "started_at"

    def duration_display(self, obj):
        if obj.ended_at:
            return f"{obj.duration_hours:.1f}h"
        return "In progress"
    duration_display.short_description = "Duration"


@admin.register(HeartRateEntry)
class HeartRateEntryAdmin(admin.ModelAdmin):
    list_display = ["user", "bpm", "context", "recorded_at", "status"]
    list_filter = ["context", "status", "recorded_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "recorded_at"


@admin.register(GlucoseEntry)
class GlucoseEntryAdmin(admin.ModelAdmin):
    list_display = ["user", "value", "unit", "context", "recorded_at", "status"]
    list_filter = ["unit", "context", "status", "recorded_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "recorded_at"
