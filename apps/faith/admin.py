# ==============================================================================
# File: apps/faith/admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Django admin configuration for faith module including reading
#              plans and Bible study tools
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Faith Admin Configuration
"""

from django.contrib import admin

from .models import (
    BibleBookmark,
    BibleHighlight,
    BibleStudyNote,
    DailyVerse,
    FaithMilestone,
    PrayerRequest,
    ReadingPlanDay,
    ReadingPlanTemplate,
    SavedVerse,
    ScriptureVerse,
    UserReadingPlan,
    UserReadingProgress,
)


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


@admin.register(SavedVerse)
class SavedVerseAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "user",
        "book_name",
        "chapter",
        "translation",
        "created_at",
    ]
    list_filter = ["translation", "book_name", "status"]
    search_fields = ["reference", "text", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


@admin.register(FaithMilestone)
class FaithMilestoneAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "milestone_type", "date"]
    list_filter = ["milestone_type", "status"]
    search_fields = ["title", "description", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "date"


# =============================================================================
# READING PLAN ADMIN
# =============================================================================


class ReadingPlanDayInline(admin.TabularInline):
    """Inline admin for reading plan days."""
    model = ReadingPlanDay
    extra = 1
    ordering = ["day_number"]


@admin.register(ReadingPlanTemplate)
class ReadingPlanTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "category",
        "difficulty",
        "duration_days",
        "is_featured",
        "is_active",
    ]
    list_filter = ["category", "difficulty", "is_featured", "is_active"]
    search_fields = ["title", "description"]
    prepopulated_fields = {"slug": ("title",)}
    list_editable = ["is_featured", "is_active"]
    inlines = [ReadingPlanDayInline]
    ordering = ["-is_featured", "title"]


@admin.register(ReadingPlanDay)
class ReadingPlanDayAdmin(admin.ModelAdmin):
    list_display = ["plan", "day_number", "title"]
    list_filter = ["plan"]
    search_fields = ["title", "plan__title"]
    ordering = ["plan", "day_number"]


@admin.register(UserReadingPlan)
class UserReadingPlanAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "template",
        "status",
        "current_day",
        "started_at",
        "completed_at",
    ]
    list_filter = ["status", "template"]
    search_fields = ["user__email", "template__title"]
    raw_id_fields = ["user"]
    date_hierarchy = "started_at"


@admin.register(UserReadingProgress)
class UserReadingProgressAdmin(admin.ModelAdmin):
    list_display = [
        "user_plan",
        "plan_day",
        "is_completed",
        "completed_at",
    ]
    list_filter = ["is_completed"]
    search_fields = ["user_plan__user__email", "user_plan__template__title"]
    raw_id_fields = ["user", "user_plan", "plan_day"]


# =============================================================================
# BIBLE STUDY TOOLS ADMIN
# =============================================================================


@admin.register(BibleHighlight)
class BibleHighlightAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "user",
        "book_name",
        "color",
        "created_at",
    ]
    list_filter = ["color", "book_name", "translation", "status"]
    search_fields = ["reference", "text", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


@admin.register(BibleBookmark)
class BibleBookmarkAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "user",
        "title",
        "book_name",
        "created_at",
    ]
    list_filter = ["book_name", "translation", "status"]
    search_fields = ["reference", "title", "notes", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


@admin.register(BibleStudyNote)
class BibleStudyNoteAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "reference",
        "user",
        "book_name",
        "created_at",
    ]
    list_filter = ["book_name", "translation", "status"]
    search_fields = ["title", "reference", "content", "user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
