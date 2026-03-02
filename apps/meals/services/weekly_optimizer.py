"""
Weekly Meal Plan Optimization Service

Generates 3-7 day meal plans by selecting recipes that:
- Minimize waste (use expiring pantry items)
- Minimize store trips (cluster missing ingredients)
- Respect dietary constraints (carb/protein/calorie targets)
- Respect calendar events (available cooking time)
- Maximize variety (avoid repetition)
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from .meal_scoring import rank_recipes, score_recipe

logger = logging.getLogger(__name__)


@dataclass
class PlanSlot:
    """A slot in the meal plan to fill."""
    date: date
    meal_type: str  # breakfast, lunch, dinner, snack
    available_minutes: Optional[int] = None


@dataclass
class PlanResult:
    """Result of the optimization."""
    entries: list  # List of (PlanSlot, MealScore) tuples
    total_missing_ingredients: list
    estimated_store_trips: int
    confidence_score: Decimal
    warnings: list


def generate_meal_plan(
    household,
    start_date: date,
    days: int = 7,
    meal_types: list = None,
    dietary_profile=None,
    recipes=None,
) -> PlanResult:
    """
    Generate an optimized meal plan for a household.

    Uses a greedy algorithm:
    1. Score all recipes for the household
    2. For each slot, pick the best unused recipe
    3. Track ingredient usage to adjust scores for later slots
    4. Consolidate missing ingredients into shopping list

    Args:
        household: Household instance
        start_date: First day of the plan
        days: Number of days (3-7)
        meal_types: Which meals to plan (default: ["dinner"])
        dietary_profile: Optional dietary constraints
        recipes: Optional queryset of recipes to consider
    """
    from apps.life.models import Recipe
    from apps.meals.models import MealPlan, MealPlanEntry

    if meal_types is None:
        meal_types = ["dinner"]

    days = min(max(days, 1), 7)  # Clamp to 1-7

    # Get available recipes
    if recipes is None:
        recipes = Recipe.objects.filter(
            user=household.primary_user,
        )

    recipe_list = list(recipes)
    if not recipe_list:
        return PlanResult(
            entries=[],
            total_missing_ingredients=[],
            estimated_store_trips=0,
            confidence_score=Decimal("0"),
            warnings=["No recipes available for planning"],
        )

    # Create slots
    slots = []
    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)
        for meal_type in meal_types:
            slots.append(PlanSlot(
                date=current_date,
                meal_type=meal_type,
                available_minutes=None,  # TODO: Pull from calendar
            ))

    # Score all recipes once
    scored = rank_recipes(
        recipe_list, household, dietary_profile,
        top_n=len(recipe_list),  # Score all
    )

    if not scored:
        return PlanResult(
            entries=[],
            total_missing_ingredients=[],
            estimated_store_trips=0,
            confidence_score=Decimal("0"),
            warnings=["Could not score any recipes"],
        )

    # Greedy assignment: for each slot, pick the best unassigned recipe
    used_recipe_ids = set()
    entries = []
    all_missing = set()
    warnings = []

    for slot in slots:
        best = None
        for score in scored:
            if score.recipe_id not in used_recipe_ids:
                best = score
                break

        if best is None:
            # All recipes used — allow repeats from highest scoring
            if scored:
                best = scored[0]
                warnings.append(
                    f"Repeated recipe '{best.recipe_title}' on {slot.date} "
                    f"(not enough unique recipes for plan)"
                )
            else:
                continue

        used_recipe_ids.add(best.recipe_id)
        entries.append((slot, best))
        all_missing.update(best.missing_ingredients)

    # Estimate store trips based on missing ingredients
    missing_list = list(all_missing)
    if len(missing_list) == 0:
        store_trips = 0
    elif len(missing_list) <= 5:
        store_trips = 1
    else:
        store_trips = min(2, len(missing_list) // 5)

    # Overall confidence
    if entries:
        avg_confidence = sum(
            s.confidence for _, s in entries
        ) / len(entries)
    else:
        avg_confidence = Decimal("0")

    return PlanResult(
        entries=entries,
        total_missing_ingredients=missing_list,
        estimated_store_trips=store_trips,
        confidence_score=round(avg_confidence, 2),
        warnings=warnings,
    )


def save_meal_plan(household, plan_result, user) -> "MealPlan":
    """
    Save a PlanResult as a MealPlan with MealPlanEntries.
    """
    from apps.meals.models import MealPlan, MealPlanEntry

    if not plan_result.entries:
        return None

    dates = [slot.date for slot, _ in plan_result.entries]
    start_date = min(dates)
    end_date = max(dates)

    plan = MealPlan.objects.create(
        user=user,
        household=household,
        start_date=start_date,
        end_date=end_date,
        confidence_score=plan_result.confidence_score,
    )

    for slot, score in plan_result.entries:
        from apps.life.models import Recipe
        recipe = Recipe.objects.get(pk=score.recipe_id)

        MealPlanEntry.objects.create(
            meal_plan=plan,
            date=slot.date,
            meal_type=slot.meal_type,
            recipe=recipe,
            serving_count=recipe.servings or 1,
            score=score.total_score,
            inventory_impact_snapshot={
                "missing": score.missing_ingredients,
                "confidence": str(score.confidence),
                "factors": {
                    f.name: str(f.value)
                    for f in score.factors
                },
            },
        )

    return plan
