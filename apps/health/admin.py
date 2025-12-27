"""
Health Admin Configuration
"""

from django.contrib import admin

from .models import (
    CardioDetails,
    Exercise,
    ExerciseSet,
    FastingWindow,
    GlucoseEntry,
    HeartRateEntry,
    PersonalRecord,
    TemplateExercise,
    WeightEntry,
    WorkoutExercise,
    WorkoutSession,
    WorkoutTemplate,
)


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


# =============================================================================
# Fitness Admin
# =============================================================================


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "muscle_group", "is_active", "created_at"]
    list_filter = ["category", "muscle_group", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category", "muscle_group", "name"]
    list_editable = ["is_active"]


class ExerciseSetInline(admin.TabularInline):
    model = ExerciseSet
    extra = 0


class CardioDetailsInline(admin.StackedInline):
    model = CardioDetails
    extra = 0
    max_num = 1


class WorkoutExerciseInline(admin.TabularInline):
    model = WorkoutExercise
    extra = 0
    raw_id_fields = ["exercise"]


@admin.register(WorkoutSession)
class WorkoutSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "date", "exercise_count", "duration_minutes", "status"]
    list_filter = ["status", "date"]
    search_fields = ["user__email", "name"]
    raw_id_fields = ["user"]
    date_hierarchy = "date"
    inlines = [WorkoutExerciseInline]


@admin.register(WorkoutExercise)
class WorkoutExerciseAdmin(admin.ModelAdmin):
    list_display = ["session", "exercise", "order"]
    list_filter = ["exercise__category"]
    raw_id_fields = ["session", "exercise"]
    inlines = [ExerciseSetInline, CardioDetailsInline]


@admin.register(PersonalRecord)
class PersonalRecordAdmin(admin.ModelAdmin):
    list_display = ["user", "exercise", "weight", "reps", "achieved_date"]
    list_filter = ["achieved_date", "exercise__category"]
    search_fields = ["user__email", "exercise__name"]
    raw_id_fields = ["user", "exercise", "workout_session"]
    date_hierarchy = "achieved_date"


class TemplateExerciseInline(admin.TabularInline):
    model = TemplateExercise
    extra = 0
    raw_id_fields = ["exercise"]


@admin.register(WorkoutTemplate)
class WorkoutTemplateAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "exercise_count", "status"]
    list_filter = ["status"]
    search_fields = ["user__email", "name"]
    raw_id_fields = ["user"]
    inlines = [TemplateExerciseInline]
