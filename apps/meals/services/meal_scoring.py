"""
Meal Scoring Engine

Ranks recipes for "What's for dinner?" using deterministic multi-factor
scoring with transparent weights. AI re-ranking is an optional layer on top.

Scoring Factors (deterministic):
- Inventory availability (0-1): What % of ingredients are in the pantry
- Expiration urgency (0-1): Does this recipe use soon-to-expire items
- Carb alignment (0-1): How well does this match dietary carb targets
- Protein alignment (0-1): How well does this match protein targets
- Calendar time match (0-1): Does prep+cook time fit the schedule
- Grocery avoidance (0-1): Can this be made without a store trip
- Historical frequency (0-1): Penalize recently made, boost favorites
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# Default scoring weights (sum to 1.0)
DEFAULT_WEIGHTS = {
    "inventory_availability": Decimal("0.25"),
    "expiration_urgency": Decimal("0.15"),
    "carb_alignment": Decimal("0.15"),
    "protein_alignment": Decimal("0.10"),
    "calendar_time_match": Decimal("0.10"),
    "grocery_avoidance": Decimal("0.15"),
    "historical_frequency": Decimal("0.10"),
}


@dataclass
class ScoreFactor:
    """Individual scoring factor with its value and weight."""
    name: str
    value: Decimal  # 0-1
    weight: Decimal
    weighted_value: Decimal
    explanation: str


@dataclass
class MealScore:
    """Complete scoring result for a recipe."""
    recipe_id: int
    recipe_title: str
    total_score: Decimal
    factors: list = field(default_factory=list)
    confidence: Decimal = Decimal("0.5")
    explanation: str = ""
    is_diabetes_safe: bool = True
    prep_time_minutes: Optional[int] = None
    missing_ingredients: list = field(default_factory=list)


def score_recipe(recipe, household, dietary_profile=None,
                 available_minutes=None, weights=None) -> MealScore:
    """
    Score a single recipe for a household.

    Args:
        recipe: Recipe instance
        household: Household instance
        dietary_profile: Optional DietaryProfile for carb/protein targets
        available_minutes: Optional time budget for cooking
        weights: Optional custom weights dict
    """
    from apps.meals.services.inventory_gap import analyze_recipe_gaps
    from apps.meals.services.recipe_nutrition import calculate_recipe_nutrition

    w = weights or DEFAULT_WEIGHTS
    factors = []

    # 1. Inventory Availability
    gap_analysis = analyze_recipe_gaps(recipe, household)
    inventory_score = gap_analysis.availability_score
    missing = [
        g.ingredient_name for g in gap_analysis.gaps
        if g.gap_type == "missing"
    ]
    factors.append(ScoreFactor(
        name="inventory_availability",
        value=inventory_score,
        weight=w["inventory_availability"],
        weighted_value=inventory_score * w["inventory_availability"],
        explanation=f"{gap_analysis.available_count}/{gap_analysis.total_ingredients} ingredients available",
    ))

    # 2. Expiration Urgency (higher is better — uses expiring items)
    urgency_score = gap_analysis.urgency_score
    factors.append(ScoreFactor(
        name="expiration_urgency",
        value=urgency_score,
        weight=w["expiration_urgency"],
        weighted_value=urgency_score * w["expiration_urgency"],
        explanation=f"{gap_analysis.expiring_count} expiring ingredients would be used",
    ))

    # 3. Carb Alignment
    carb_score = Decimal("0.5")  # Neutral default
    is_diabetes_safe = True
    nutrition = calculate_recipe_nutrition(recipe)

    if dietary_profile and dietary_profile.carb_limit_daily and nutrition.confidence > Decimal("0.3"):
        carbs_per_serving = nutrition.per_serving.get("carbohydrates_g", Decimal("0"))
        # Score based on how well carbs fit within 1/3 of daily limit (for a meal)
        meal_carb_budget = dietary_profile.carb_limit_daily / 3
        if meal_carb_budget > 0:
            ratio = carbs_per_serving / meal_carb_budget
            if ratio <= Decimal("1.0"):
                carb_score = Decimal("1.0") - (ratio * Decimal("0.3"))
            else:
                carb_score = max(Decimal("0"), Decimal("1.0") - ratio)

        if dietary_profile.diabetes_sensitive and carbs_per_serving > Decimal("45"):
            is_diabetes_safe = False
            carb_score = max(Decimal("0"), carb_score - Decimal("0.3"))

    factors.append(ScoreFactor(
        name="carb_alignment",
        value=carb_score,
        weight=w["carb_alignment"],
        weighted_value=carb_score * w["carb_alignment"],
        explanation=f"Carb alignment: {carb_score}",
    ))

    # 4. Protein Alignment
    protein_score = Decimal("0.5")
    if dietary_profile and dietary_profile.protein_target_daily and nutrition.confidence > Decimal("0.3"):
        protein_per_serving = nutrition.per_serving.get("protein_g", Decimal("0"))
        meal_protein_target = dietary_profile.protein_target_daily / 3
        if meal_protein_target > 0:
            ratio = protein_per_serving / meal_protein_target
            if ratio >= Decimal("0.8"):
                protein_score = min(Decimal("1.0"), ratio * Decimal("0.8"))
            else:
                protein_score = ratio * Decimal("0.8")

    factors.append(ScoreFactor(
        name="protein_alignment",
        value=protein_score,
        weight=w["protein_alignment"],
        weighted_value=protein_score * w["protein_alignment"],
        explanation=f"Protein alignment: {protein_score}",
    ))

    # 5. Calendar Time Match
    time_score = Decimal("0.5")
    total_time = recipe.total_time_minutes
    if available_minutes is not None and total_time:
        if total_time <= available_minutes:
            time_score = Decimal("1.0")
        elif total_time <= available_minutes * 1.5:
            time_score = Decimal("0.5")
        else:
            time_score = Decimal("0.1")

    factors.append(ScoreFactor(
        name="calendar_time_match",
        value=time_score,
        weight=w["calendar_time_match"],
        weighted_value=time_score * w["calendar_time_match"],
        explanation=f"Time: {total_time or '?'} min vs {available_minutes or '?'} min available",
    ))

    # 6. Grocery Avoidance
    grocery_score = inventory_score  # Same as availability for now
    if gap_analysis.missing_count == 0:
        grocery_score = Decimal("1.0")
    elif gap_analysis.missing_count <= 2:
        grocery_score = Decimal("0.5")
    else:
        grocery_score = Decimal("0.1")

    factors.append(ScoreFactor(
        name="grocery_avoidance",
        value=grocery_score,
        weight=w["grocery_avoidance"],
        weighted_value=grocery_score * w["grocery_avoidance"],
        explanation=f"{gap_analysis.missing_count} ingredients need purchasing",
    ))

    # 7. Historical Frequency (penalize recently made)
    frequency_score = _compute_frequency_score(recipe, household)
    factors.append(ScoreFactor(
        name="historical_frequency",
        value=frequency_score,
        weight=w["historical_frequency"],
        weighted_value=frequency_score * w["historical_frequency"],
        explanation=f"Freshness score: {frequency_score}",
    ))

    # Compute total
    total = sum(f.weighted_value for f in factors)
    total = round(min(total, Decimal("1.0")), 3)

    # Build explanation
    top_factors = sorted(factors, key=lambda f: f.weighted_value, reverse=True)[:3]
    explanation_parts = [f"{f.name}: {f.explanation}" for f in top_factors]
    explanation = " | ".join(explanation_parts)

    return MealScore(
        recipe_id=recipe.id,
        recipe_title=recipe.title,
        total_score=total,
        factors=factors,
        confidence=nutrition.confidence,
        explanation=explanation,
        is_diabetes_safe=is_diabetes_safe,
        prep_time_minutes=total_time,
        missing_ingredients=missing,
    )


def _compute_frequency_score(recipe, household) -> Decimal:
    """
    Score based on how recently/frequently this recipe was used.

    Higher score = less recently used (more variety).
    """
    from apps.meals.models import MealPlanEntry

    # Check recent meal plan entries
    recent = MealPlanEntry.objects.filter(
        meal_plan__household=household,
        recipe=recipe,
        date__gte=timezone.now().date() - timezone.timedelta(days=14),
    ).count()

    if recent == 0:
        # Boost favorites that haven't been made recently
        return Decimal("0.9") if recipe.is_favorite else Decimal("0.7")
    elif recent == 1:
        return Decimal("0.4")
    else:
        return Decimal("0.1")  # Made multiple times recently


def rank_recipes(recipes, household, dietary_profile=None,
                 available_minutes=None, top_n=10) -> list[MealScore]:
    """
    Score and rank multiple recipes for a household.

    Returns top_n recipes sorted by score descending.
    """
    scores = []
    for recipe in recipes:
        try:
            score = score_recipe(
                recipe, household, dietary_profile, available_minutes,
            )
            scores.append(score)
        except Exception as e:
            logger.warning(f"Error scoring recipe {recipe.id}: {e}")
            continue

    # Sort by total score descending
    scores.sort(key=lambda s: s.total_score, reverse=True)
    return scores[:top_n]
