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
    Medicine,
    MedicineLog,
    MedicineSchedule,
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


# =============================================================================
# Medicine Admin
# =============================================================================


class MedicineScheduleInline(admin.TabularInline):
    model = MedicineSchedule
    extra = 1


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "user",
        "dose",
        "frequency",
        "medicine_status",
        "needs_refill_display",
        "start_date",
        "status",
    ]
    list_filter = ["medicine_status", "frequency", "is_prn", "status", "start_date"]
    search_fields = ["user__email", "name", "purpose", "prescribing_doctor"]
    raw_id_fields = ["user"]
    date_hierarchy = "start_date"
    inlines = [MedicineScheduleInline]

    fieldsets = (
        (None, {
            "fields": ("user", "name", "purpose", "dose")
        }),
        ("Scheduling", {
            "fields": ("frequency", "is_prn", "start_date", "end_date", "grace_period_minutes")
        }),
        ("Status", {
            "fields": ("medicine_status", "paused_at", "paused_reason")
        }),
        ("Refill Tracking", {
            "fields": ("current_supply", "refill_threshold")
        }),
        ("Prescription Details", {
            "fields": ("prescribing_doctor", "pharmacy", "rx_number"),
            "classes": ("collapse",)
        }),
        ("Notes", {
            "fields": ("instructions", "notes")
        }),
    )

    def needs_refill_display(self, obj):
        if obj.needs_refill:
            return "⚠️ Low Supply"
        if obj.current_supply is not None:
            return f"{obj.current_supply} doses"
        return "—"
    needs_refill_display.short_description = "Supply"


@admin.register(MedicineSchedule)
class MedicineScheduleAdmin(admin.ModelAdmin):
    list_display = ["medicine", "scheduled_time", "label", "days_of_week", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["medicine__name", "label"]
    raw_id_fields = ["medicine"]


@admin.register(MedicineLog)
class MedicineLogAdmin(admin.ModelAdmin):
    list_display = [
        "medicine",
        "user",
        "scheduled_date",
        "scheduled_time",
        "log_status",
        "taken_at",
        "is_prn_dose",
    ]
    list_filter = ["log_status", "is_prn_dose", "scheduled_date", "status"]
    search_fields = ["user__email", "medicine__name", "notes"]
    raw_id_fields = ["user", "medicine", "schedule"]
    date_hierarchy = "scheduled_date"
