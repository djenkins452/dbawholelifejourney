from django.contrib import admin

from .models import (
    DietaryProfile,
    Household,
    HouseholdMembership,
    Ingredient,
    InventoryTransaction,
    MealPlan,
    MealPlanEntry,
    PantryItem,
    Receipt,
    ReceiptItem,
    RecipeIngredient,
)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ["canonical_name", "category", "storage_type", "shelf_life_days"]
    list_filter = ["category", "storage_type"]
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
    list_display = ["ingredient", "household", "quantity", "unit", "confidence_score"]
    list_filter = ["household"]
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
