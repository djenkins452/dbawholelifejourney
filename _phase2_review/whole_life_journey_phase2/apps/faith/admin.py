"""
Faith Admin Configuration
"""

from django.contrib import admin

from .models import DailyVerse, FaithMilestone, PrayerRequest, ScriptureVerse


@admin.register(ScriptureVerse)
class ScriptureVerseAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "book_name",
        "chapter",
        "translation",
        "is_active",
    ]
    list_filter = ["translation", "book_name", "is_active"]
    search_fields = ["reference", "text"]
    list_editable = ["is_active"]
    ordering = ["book_order", "chapter", "verse_start"]


@admin.register(DailyVerse)
class DailyVerseAdmin(admin.ModelAdmin):
    list_display = ["date", "verse", "theme"]
    list_filter = ["date"]
    search_fields = ["verse__reference", "theme"]
    date_hierarchy = "date"
    raw_id_fields = ["verse"]


@admin.register(PrayerRequest)
class PrayerRequestAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "user",
        "priority",
        "is_answered",
        "created_at",
    ]
    list_filter = ["is_answered", "priority", "is_personal", "status"]
    search_fields = ["title", "description", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"


@admin.register(FaithMilestone)
class FaithMilestoneAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "milestone_type", "date"]
    list_filter = ["milestone_type", "status"]
    search_fields = ["title", "description", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "date"
