"""
Recipe Nutrition Service

Calculates per-serving nutrition for recipes by aggregating
RecipeIngredient → Ingredient → FoodItem nutrient data.

Uses the existing nutrition_calculator from health app for consistency.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Nutrient fields we track (matching health app's nutrition_calculator)
NUTRIENT_FIELDS = [
    "calories", "protein_g", "carbohydrates_g", "fiber_g", "sugar_g",
    "fat_g", "saturated_fat_g", "unsaturated_fat_g", "trans_fat_g",
    "sodium_mg", "cholesterol_mg", "potassium_mg", "calcium_mg", "iron_mg",
    "vitamin_a_iu", "vitamin_c_mg", "vitamin_d_iu", "vitamin_b12_mcg",
]

CACHE_PREFIX = "meal_recipe_nutrition"
CACHE_TIMEOUT = 3600  # 1 hour


@dataclass
class RecipeNutrition:
    """Nutrition totals and per-serving values for a recipe."""
    recipe_id: int
    servings: int
    total: dict = field(default_factory=dict)
    per_serving: dict = field(default_factory=dict)
    ingredient_count: int = 0
    linked_count: int = 0  # How many ingredients have FoodItem links
    confidence: Decimal = Decimal("0")
    warnings: list = field(default_factory=list)
    is_diabetes_flagged: bool = False


def _zero_nutrients() -> dict:
    """Return a dict of all nutrient fields set to 0."""
    return {f: Decimal("0") for f in NUTRIENT_FIELDS}


def _get_food_item_nutrients(food_item) -> dict:
    """Extract per-serving nutrients from a FoodItem."""
    nutrients = {}
    for f in NUTRIENT_FIELDS:
        val = getattr(food_item, f, None)
        if val is not None:
            nutrients[f] = Decimal(str(val))
        else:
            nutrients[f] = Decimal("0")
    return nutrients


def calculate_recipe_nutrition(recipe, use_cache=True) -> RecipeNutrition:
    """
    Calculate total and per-serving nutrition for a recipe.

    Aggregates nutrients from each RecipeIngredient's linked FoodItem.
    Results are cached and invalidated when ingredients change.
    """
    from apps.meals.models import RecipeIngredient

    cache_key = f"{CACHE_PREFIX}:{recipe.id}"

    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    servings = recipe.servings or 1
    totals = _zero_nutrients()
    warnings = []
    ingredient_count = 0
    linked_count = 0

    structured = (
        RecipeIngredient.objects
        .filter(recipe=recipe)
        .select_related("ingredient", "ingredient__nutrition_source")
    )

    for ri in structured:
        ingredient_count += 1
        food_item = ri.ingredient.nutrition_source

        if food_item is None:
            warnings.append(
                f"No nutrition data for '{ri.ingredient.canonical_name}'"
            )
            continue

        linked_count += 1
        nutrients = _get_food_item_nutrients(food_item)

        # Scale by quantity (if provided)
        # Assumes ingredient quantity maps to food_item servings
        # e.g., "2 cups flour" → 2 servings of flour's FoodItem
        qty = ri.quantity or Decimal("1")

        for field_name, value in nutrients.items():
            totals[field_name] += value * qty

    # Per-serving calculation
    per_serving = {}
    for field_name, total_val in totals.items():
        per_serving[field_name] = round(total_val / Decimal(str(servings)), 2)

    # Confidence based on how many ingredients have nutrition links
    if ingredient_count > 0:
        confidence = Decimal(str(
            round(linked_count / ingredient_count, 2)
        ))
    else:
        confidence = Decimal("0")

    # Diabetes flag: check if per-serving carbs exceed threshold
    carbs_per_serving = per_serving.get("carbohydrates_g", Decimal("0"))
    is_diabetes_flagged = carbs_per_serving > Decimal("45")

    if is_diabetes_flagged:
        warnings.append(
            f"High carbs per serving ({carbs_per_serving}g) — "
            f"may not be suitable for diabetes-sensitive diets"
        )

    result = RecipeNutrition(
        recipe_id=recipe.id,
        servings=servings,
        total={k: round(v, 2) for k, v in totals.items()},
        per_serving=per_serving,
        ingredient_count=ingredient_count,
        linked_count=linked_count,
        confidence=confidence,
        warnings=warnings,
        is_diabetes_flagged=is_diabetes_flagged,
    )

    if use_cache:
        cache.set(cache_key, result, CACHE_TIMEOUT)

    return result


def invalidate_recipe_nutrition_cache(recipe_id: int):
    """Invalidate cached nutrition for a recipe."""
    cache_key = f"{CACHE_PREFIX}:{recipe_id}"
    cache.delete(cache_key)
    logger.info(f"Invalidated nutrition cache for recipe {recipe_id}")


def get_recipe_macro_summary(recipe) -> Optional[dict]:
    """
    Quick macro summary for display (calories, protein, carbs, fat per serving).
    """
    nutrition = calculate_recipe_nutrition(recipe)
    if nutrition.confidence < Decimal("0.3"):
        return None

    ps = nutrition.per_serving
    return {
        "calories": float(ps.get("calories", 0)),
        "protein_g": float(ps.get("protein_g", 0)),
        "carbohydrates_g": float(ps.get("carbohydrates_g", 0)),
        "fat_g": float(ps.get("fat_g", 0)),
        "fiber_g": float(ps.get("fiber_g", 0)),
        "confidence": float(nutrition.confidence),
        "is_diabetes_flagged": nutrition.is_diabetes_flagged,
        "servings": nutrition.servings,
    }
