from django.contrib import admin

from .models import (
    DietaryProfile,
    Household,
    HouseholdMembership,
    Ingredient,
    FoodWasteEvent,
    InventoryTransaction,
    Leftover,
    MealConsumption,
    MealPlan,
    MealPlanEntry,
    PantryItem,
    PreparationEvent,
    Receipt,
    ReceiptItem,
    RecipeIngredient,
)


@admin.register(MealConsumption)
class MealConsumptionAdmin(admin.ModelAdmin):
    list_display = ("recipe_title", "user", "servings_consumed", "meal_type",
                    "consumed_at", "food_entry")
    search_fields = ("recipe_title", "idempotency_key")
    date_hierarchy = "consumed_at"


@admin.register(PreparationEvent)
class PreparationEventAdmin(admin.ModelAdmin):
    list_display = ("recipe_title", "household", "preparation_status",
                    "deduction_status", "servings_prepared", "prepared_at")
    list_filter = ("preparation_status", "deduction_status")
    search_fields = ("recipe_title", "idempotency_key")
    readonly_fields = ("deduction_summary",)
    date_hierarchy = "prepared_at"


@admin.register(Leftover)
class LeftoverAdmin(admin.ModelAdmin):
    list_display = ("recipe_title", "household", "servings", "disposition",
                    "expiration_date", "created_at")
    list_filter = ("disposition",)
    search_fields = ("recipe_title",)


@admin.register(FoodWasteEvent)
class FoodWasteEventAdmin(admin.ModelAdmin):
    list_display = ("recipe_title", "household", "event_type", "servings",
                    "source", "occurred_at")
    list_filter = ("event_type", "source")
    search_fields = ("recipe_title", "idempotency_key")
    date_hierarchy = "occurred_at"


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    # base_measure + density_g_per_ml are the canonical Container Truth substance
    # properties that let package units bridge to culinary units during preparation.
    list_display = ["canonical_name", "category", "base_measure", "density_g_per_ml",
                    "storage_type", "shelf_life_days"]
    list_filter = ["category", "storage_type", "base_measure"]
    search_fields = ["canonical_name", "aliases"]


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 0
    autocomplete_fields = ["ingredient"]


@admin.register(RecipeIngredient)
class RecipeIngredientAdmin(admin.ModelAdmin):
    list_display = ["recipe", "ingredient", "quantity", "unit", "order_index"]
    list_filter = ["unit"]
    autocomplete_fields = ["recipe", "ingredient"]


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name", "primary_user", "grocery_cycle_days"]
    search_fields = ["name"]


@admin.register(HouseholdMembership)
class HouseholdMembershipAdmin(admin.ModelAdmin):
    list_display = ["household", "user", "role"]
    list_filter = ["role"]


@admin.register(DietaryProfile)
class DietaryProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "carb_limit_daily", "protein_target_daily", "diabetes_sensitive"]
    list_filter = ["diabetes_sensitive"]


@admin.register(PantryItem)
class PantryItemAdmin(admin.ModelAdmin):
    # net_content / net_content_unit = Container Truth (stable contents of one full
    # container); quantity = Remaining Truth (how many containers are left, fractional).
    list_display = ["ingredient", "household", "quantity", "unit",
                    "net_content", "net_content_unit", "container_type", "confidence_score"]
    list_filter = ["household", "container_type"]
    search_fields = ["ingredient__canonical_name"]


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ["pantry_item", "delta_quantity", "source", "created_at"]
    list_filter = ["source"]


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ["household", "start_date", "end_date", "confidence_score"]
    list_filter = ["household"]


@admin.register(MealPlanEntry)
class MealPlanEntryAdmin(admin.ModelAdmin):
    list_display = ["meal_plan", "date", "meal_type", "recipe", "score"]
    list_filter = ["meal_type"]


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ["store", "receipt_date", "total", "household"]
    list_filter = ["household"]


@admin.register(ReceiptItem)
class ReceiptItemAdmin(admin.ModelAdmin):
    list_display = ["raw_name", "ingredient", "quantity", "unit", "match_confidence"]
    list_filter = ["match_confidence"]
