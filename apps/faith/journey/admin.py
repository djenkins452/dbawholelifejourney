"""
Journey admin — separate from existing reading-plan admin.

Registers the three content models (JourneyPath, JourneyArc, JourneyDay).
User-state models (UserJourney, UserJourneyDayProgress) are admin-registered
in Phase 1 read-only-friendly mode; user data should be edited through the
service layer, not the admin.
"""

from django.contrib import admin

from apps.faith.journey.models import (
    JourneyPath,
    JourneyArc,
    JourneyDay,
    UserJourney,
    UserJourneyDayProgress,
)


class JourneyArcInline(admin.TabularInline):
    model = JourneyArc
    extra = 0
    fields = ("order", "slug", "name", "era_label", "estimated_days", "is_active")
    show_change_link = True


@admin.register(JourneyPath)
class JourneyPathAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "is_featured", "difficulty_default", "estimated_weeks", "updated_at")
    list_filter = ("is_active", "is_featured", "difficulty_default")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    inlines = [JourneyArcInline]


@admin.register(JourneyArc)
class JourneyArcAdmin(admin.ModelAdmin):
    list_display = ("name", "journey_path", "order", "era_label", "estimated_days", "is_active", "updated_at")
    list_filter = ("is_active", "journey_path", "era_label")
    search_fields = ("name", "slug", "era_label")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("journey_path", "order")


@admin.register(JourneyDay)
class JourneyDayAdmin(admin.ModelAdmin):
    list_display = ("arc", "day_number", "scripture_refs_display", "key_insight_truncated", "updated_at")
    list_filter = ("arc__journey_path", "arc")
    search_fields = ("arc__name", "key_insight", "scripture_refs")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("arc", "day_number")

    fieldsets = (
        ("Position", {"fields": ("arc", "day_number")}),
        ("Scripture", {"fields": ("scripture_refs", "scripture_content")}),
        ("Context", {"fields": ("context_before",)}),
        ("Plain English tiers", {
            "fields": ("plain_english_simple", "plain_english_standard", "plain_english_deeper"),
        }),
        ("Synthesis", {"fields": ("key_insight", "reflection_prompt", "application_action")}),
        ("Confusion & retention", {"fields": ("confusion_topics", "retention_anchor")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def scripture_refs_display(self, obj):
        refs = obj.scripture_refs or []
        return ", ".join(refs) if isinstance(refs, list) else str(refs)

    scripture_refs_display.short_description = "Scripture"

    def key_insight_truncated(self, obj):
        if len(obj.key_insight) > 80:
            return obj.key_insight[:77] + "..."
        return obj.key_insight

    key_insight_truncated.short_description = "Key insight"


@admin.register(UserJourney)
class UserJourneyAdmin(admin.ModelAdmin):
    list_display = ("user", "journey_path", "current_arc", "current_day_number", "journey_status", "preferred_difficulty", "last_engaged_at")
    list_filter = ("journey_status", "preferred_difficulty", "journey_path")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at", "started_at", "last_engaged_at", "completed_at", "momentum_score")


@admin.register(UserJourneyDayProgress)
class UserJourneyDayProgressAdmin(admin.ModelAdmin):
    list_display = ("user_journey", "journey_day", "is_completed", "application_committed", "difficulty_at_completion", "completed_at")
    list_filter = ("is_completed", "application_committed", "difficulty_at_completion")
    search_fields = ("user_journey__user__email",)
    readonly_fields = ("created_at", "updated_at", "completed_at")
