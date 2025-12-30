"""
Health Admin Configuration
"""

from django.contrib import admin

from .models import (
    CardioDetails,
    CustomFood,
    DailyNutritionSummary,
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
