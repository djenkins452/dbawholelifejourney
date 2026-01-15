"""
Health Admin Configuration
"""

from django.contrib import admin

from .models import (
    CardioDetails,
    CustomFood,
    Cycle,
    CycleDailyLog,
    CyclePrediction,
    CycleSettings,
    DailyNutritionSummary,
    DexcomCredential,
    Exercise,
    ExerciseSet,
    FastingWindow,
    FoodEntry,
    FoodItem,
    GlucoseEntry,
    HeartRateEntry,
    MedicalProvider,
    Medicine,
    MedicineLog,
    MedicineSchedule,
    NutritionGoals,
    PersonalRecord,
    ProviderStaff,
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
    list_display = ["user", "value", "unit", "trend_arrow", "context", "source", "recorded_at", "status"]
    list_filter = ["unit", "context", "source", "status", "recorded_at"]
    search_fields = ["user__email", "dexcom_record_id"]
    raw_id_fields = ["user"]
    date_hierarchy = "recorded_at"
    readonly_fields = ["dexcom_record_id", "display_device"]

    def trend_arrow(self, obj):
        return obj.trend_arrow_display or "-"
    trend_arrow.short_description = "Trend"

    fieldsets = (
        (None, {
            'fields': ('user', 'value', 'unit', 'context', 'recorded_at', 'notes', 'status')
        }),
        ('Dexcom Data', {
            'classes': ('collapse',),
            'fields': ('source', 'dexcom_record_id', 'trend', 'trend_rate', 'display_device')
        }),
    )


@admin.register(DexcomCredential)
class DexcomCredentialAdmin(admin.ModelAdmin):
    list_display = ["user", "is_connected", "sync_enabled", "last_sync", "last_sync_status"]
    list_filter = ["sync_enabled", "last_sync_status"]
    search_fields = ["user__email", "dexcom_user_id"]
    raw_id_fields = ["user"]
    readonly_fields = ["access_token", "refresh_token", "token_expiry", "dexcom_user_id",
                       "last_sync", "last_sync_status", "last_sync_message", "last_sync_count",
                       "created_at", "updated_at"]

    fieldsets = (
        (None, {
            'fields': ('user', 'sync_enabled', 'days_to_sync')
        }),
        ('OAuth Tokens (Read Only)', {
            'classes': ('collapse',),
            'fields': ('access_token', 'refresh_token', 'token_expiry', 'dexcom_user_id')
        }),
        ('Sync Status', {
            'fields': ('last_sync', 'last_sync_status', 'last_sync_message', 'last_sync_count')
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        }),
    )

    def is_connected(self, obj):
        return obj.is_connected
    is_connected.boolean = True
    is_connected.short_description = "Connected"


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


# =============================================================================
# Nutrition / Food Tracking Admin
# =============================================================================


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "brand",
        "calories",
        "protein_g",
        "carbohydrates_g",
        "fat_g",
        "data_source",
        "is_verified",
        "is_active",
    ]
    list_filter = ["data_source", "is_verified", "is_active", "is_vegan", "is_gluten_free"]
    search_fields = ["name", "brand", "barcode"]
    list_editable = ["is_verified", "is_active"]
    ordering = ["name"]

    fieldsets = (
        (None, {
            "fields": ("name", "brand", "description", "barcode")
        }),
        ("Source", {
            "fields": ("data_source", "source_reference", "is_verified")
        }),
        ("Serving", {
            "fields": ("serving_size", "serving_unit", "servings_per_container")
        }),
        ("Macronutrients", {
            "fields": (
                "calories",
                ("protein_g", "carbohydrates_g", "fat_g"),
                ("fiber_g", "sugar_g"),
                ("saturated_fat_g", "unsaturated_fat_g", "trans_fat_g"),
            )
        }),
        ("Micronutrients", {
            "fields": (
                ("sodium_mg", "cholesterol_mg", "potassium_mg"),
                ("calcium_mg", "iron_mg"),
                ("vitamin_a_iu", "vitamin_c_mg", "vitamin_d_iu", "vitamin_b12_mcg"),
            ),
            "classes": ("collapse",)
        }),
        ("Dietary Attributes", {
            "fields": (
                ("is_vegan", "is_vegetarian", "is_keto_friendly"),
                ("is_gluten_free", "is_dairy_free", "is_nut_free"),
                ("is_low_sodium", "is_low_carb"),
            ),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )


@admin.register(CustomFood)
class CustomFoodAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "user",
        "calories",
        "protein_g",
        "carbohydrates_g",
        "fat_g",
        "serving_size",
        "serving_unit",
        "is_recipe",
        "status",
    ]
    list_filter = ["is_recipe", "status"]
    search_fields = ["user__email", "name", "description"]
    raw_id_fields = ["user"]
    ordering = ["name"]


@admin.register(FoodEntry)
class FoodEntryAdmin(admin.ModelAdmin):
    list_display = [
        "food_name",
        "user",
        "logged_date",
        "meal_type",
        "total_calories",
        "total_protein_g",
        "total_carbohydrates_g",
        "total_fat_g",
        "entry_source",
        "status",
    ]
    list_filter = ["meal_type", "entry_source", "location", "status", "logged_date"]
    search_fields = ["user__email", "food_name", "food_brand", "notes"]
    raw_id_fields = ["user", "food_item", "custom_food"]
    date_hierarchy = "logged_date"
    ordering = ["-logged_date", "-logged_time"]

    fieldsets = (
        (None, {
            "fields": ("user", "food_name", "food_brand")
        }),
        ("Food Reference", {
            "fields": ("food_item", "custom_food")
        }),
        ("Quantity", {
            "fields": ("quantity", "serving_size", "serving_unit")
        }),
        ("Nutrition (totals)", {
            "fields": (
                "total_calories",
                ("total_protein_g", "total_carbohydrates_g", "total_fat_g"),
                ("total_fiber_g", "total_sugar_g", "total_saturated_fat_g"),
                ("total_sodium_mg", "total_cholesterol_mg", "total_potassium_mg"),
            )
        }),
        ("Timing", {
            "fields": ("logged_date", "logged_time", "meal_type")
        }),
        ("Context", {
            "fields": (
                ("location", "eating_pace"),
                ("hunger_level_before", "fullness_level_after"),
                "mood_tags",
                "notes",
            ),
            "classes": ("collapse",)
        }),
        ("Tracking", {
            "fields": ("entry_source", "ai_confidence_score")
        }),
    )


@admin.register(DailyNutritionSummary)
class DailyNutritionSummaryAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "summary_date",
        "total_calories",
        "total_protein_g",
        "total_carbohydrates_g",
        "total_fat_g",
        "total_entry_count",
        "calculation_version",
    ]
    list_filter = ["summary_date"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "summary_date"
    ordering = ["-summary_date"]

    readonly_fields = [
        "calculation_version",
        "last_recalculated",
        "protein_percentage",
        "carb_percentage",
        "fat_percentage",
    ]


@admin.register(NutritionGoals)
class NutritionGoalsAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "daily_calorie_target",
        "daily_protein_target_g",
        "daily_carb_target_g",
        "daily_fat_target_g",
        "effective_from",
        "effective_until",
        "status",
    ]
    list_filter = ["effective_from", "status"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "effective_from"

    fieldsets = (
        (None, {
            "fields": ("user",)
        }),
        ("Calorie Target", {
            "fields": ("daily_calorie_target",)
        }),
        ("Macro Targets", {
            "fields": (
                ("daily_protein_target_g", "daily_carb_target_g", "daily_fat_target_g"),
                "daily_fiber_target_g",
            )
        }),
        ("Limits", {
            "fields": ("daily_sodium_limit_mg", "daily_sugar_limit_g")
        }),
        ("Dietary Preferences", {
            "fields": ("dietary_preferences", "allergies"),
            "classes": ("collapse",)
        }),
        ("Active Period", {
            "fields": ("effective_from", "effective_until")
        }),
        ("Notes", {
            "fields": ("notes",)
        }),
    )


# =============================================================================
# Medical Provider Admin
# =============================================================================


class ProviderStaffInline(admin.TabularInline):
    model = ProviderStaff
    extra = 1
    raw_id_fields = ["user"]
    fields = ["name", "role", "title", "phone_extension", "direct_phone", "email"]


@admin.register(MedicalProvider)
class MedicalProviderAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "user",
        "specialty",
        "credentials",
        "phone",
        "city",
        "state",
        "is_primary",
        "ai_lookup_completed",
        "status",
    ]
    list_filter = ["specialty", "is_primary", "accepts_insurance", "ai_lookup_completed", "status"]
    search_fields = ["user__email", "name", "phone", "city", "npi_number"]
    raw_id_fields = ["user"]
    inlines = [ProviderStaffInline]
    ordering = ["name"]

    fieldsets = (
        (None, {
            "fields": ("user", "name", "specialty", "credentials", "is_primary")
        }),
        ("Contact Information", {
            "fields": (
                ("phone", "phone_alt"),
                ("fax", "email"),
                "website",
            )
        }),
        ("Address", {
            "fields": (
                "address_line1",
                "address_line2",
                ("city", "state"),
                ("postal_code", "country"),
            )
        }),
        ("Patient Portal", {
            "fields": ("portal_url", "portal_username"),
            "classes": ("collapse",)
        }),
        ("Insurance & Billing", {
            "fields": ("npi_number", "accepts_insurance", "insurance_notes"),
            "classes": ("collapse",)
        }),
        ("Notes", {
            "fields": ("notes",)
        }),
        ("AI Lookup", {
            "fields": ("ai_lookup_completed", "ai_lookup_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(ProviderStaff)
class ProviderStaffAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "provider",
        "role",
        "title",
        "phone_extension",
        "email",
        "status",
    ]
    list_filter = ["role", "status"]
    search_fields = ["name", "provider__name", "email"]
    raw_id_fields = ["user", "provider"]
    ordering = ["provider__name", "name"]


# =============================================================================
# Cycle Tracking Admin
# =============================================================================


class AverageCycleLengthFilter(admin.SimpleListFilter):
    """Filter CycleSettings by average cycle length range."""

    title = "average cycle length"
    parameter_name = "avg_cycle_length"

    def lookups(self, request, model_admin):
        return [
            ("short", "Short (< 25 days)"),
            ("normal", "Normal (25-35 days)"),
            ("long", "Long (> 35 days)"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "short":
            return queryset.filter(average_cycle_length__lt=25)
        if self.value() == "normal":
            return queryset.filter(average_cycle_length__gte=25, average_cycle_length__lte=35)
        if self.value() == "long":
            return queryset.filter(average_cycle_length__gt=35)
        return queryset


class LastLogDateFilter(admin.SimpleListFilter):
    """Filter CycleDailyLog by recency of logging."""

    title = "last log recency"
    parameter_name = "log_recency"

    def lookups(self, request, model_admin):
        return [
            ("today", "Today"),
            ("week", "Last 7 days"),
            ("month", "Last 30 days"),
            ("older", "Older than 30 days"),
        ]

    def queryset(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        if self.value() == "today":
            return queryset.filter(log_date=today)
        if self.value() == "week":
            return queryset.filter(log_date__gte=today - timedelta(days=7))
        if self.value() == "month":
            return queryset.filter(log_date__gte=today - timedelta(days=30))
        if self.value() == "older":
            return queryset.filter(log_date__lt=today - timedelta(days=30))
        return queryset


class CycleDateRangeFilter(admin.SimpleListFilter):
    """Filter Cycle by start date range."""

    title = "cycle date range"
    parameter_name = "date_range"

    def lookups(self, request, model_admin):
        return [
            ("current", "Current cycle (ongoing)"),
            ("3months", "Last 3 months"),
            ("6months", "Last 6 months"),
            ("year", "Last year"),
        ]

    def queryset(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        if self.value() == "current":
            return queryset.filter(end_date__isnull=True)
        if self.value() == "3months":
            return queryset.filter(start_date__gte=today - timedelta(days=90))
        if self.value() == "6months":
            return queryset.filter(start_date__gte=today - timedelta(days=180))
        if self.value() == "year":
            return queryset.filter(start_date__gte=today - timedelta(days=365))
        return queryset


def export_cycle_data_for_support(modeladmin, request, queryset):
    """
    Bulk action to export selected cycle data for support review.
    Exports as a downloadable CSV file.
    """
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=cycle_data_export.csv"

    writer = csv.writer(response)
    writer.writerow([
        "User Email",
        "Cycle Number",
        "Start Date",
        "End Date",
        "Period End Date",
        "Cycle Length",
        "Period Length",
        "Is Predicted",
        "Notes",
    ])

    for cycle in queryset.select_related("user"):
        writer.writerow([
            cycle.user.email,
            cycle.cycle_number,
            cycle.start_date,
            cycle.end_date or "",
            cycle.period_end_date or "",
            cycle.cycle_length or "",
            cycle.period_length or "",
            "Yes" if cycle.is_predicted else "No",
            cycle.notes,
        ])

    return response


export_cycle_data_for_support.short_description = "Export selected cycles for support review"


@admin.register(CycleSettings)
class CycleSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "cycle_tracking_enabled",
        "average_cycle_length",
        "average_period_length",
        "notifications_enabled",
        "fertile_window_tracking_enabled",
    ]
    list_filter = [
        "cycle_tracking_enabled",
        "notifications_enabled",
        "fertile_window_tracking_enabled",
        AverageCycleLengthFilter,
    ]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]


@admin.register(CycleDailyLog)
class CycleDailyLogAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "log_date",
        "flow_level",
        "mood",
        "energy_level",
        "is_period_day",
        "status",
    ]
    list_filter = ["flow_level", "mood", LastLogDateFilter, "status"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "log_date"

    def is_period_day(self, obj):
        return obj.is_period_day
    is_period_day.boolean = True
    is_period_day.short_description = "Period Day"


@admin.register(Cycle)
class CycleAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "cycle_number",
        "start_date",
        "end_date",
        "cycle_length_display",
        "period_length",
        "is_predicted",
        "status",
    ]
    list_filter = ["is_predicted", CycleDateRangeFilter, "status"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    actions = [export_cycle_data_for_support]

    def cycle_length_display(self, obj):
        length = obj.cycle_length
        return f"{length} days" if length else "Ongoing"
    cycle_length_display.short_description = "Cycle Length"


@admin.register(CyclePrediction)
class CyclePredictionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "predicted_period_start",
        "predicted_period_end",
        "prediction_confidence",
        "prediction_algorithm_version",
        "generated_at",
        "is_verified",
    ]
    list_filter = ["prediction_algorithm_version", "generated_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
    date_hierarchy = "generated_at"
    ordering = ["-generated_at"]

    def is_verified(self, obj):
        return obj.is_verified
    is_verified.boolean = True
    is_verified.short_description = "Verified"
