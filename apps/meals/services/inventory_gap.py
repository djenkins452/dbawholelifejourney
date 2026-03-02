"""
Inventory Gap Service

Compares recipe ingredient requirements against household pantry stock.
Returns missing, partial, and expiring ingredients for meal planning decisions.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class IngredientGap:
    """Describes the gap between what's needed and what's available."""
    ingredient_id: int
    ingredient_name: str
    needed_quantity: Decimal
    needed_unit: str
    available_quantity: Decimal
    available_unit: str
    confidence: Decimal
    gap_type: str  # "missing", "partial", "expiring", "available"
    days_until_expiration: Optional[int] = None


@dataclass
class GapAnalysis:
    """Complete gap analysis for a recipe against a household pantry."""
    recipe_id: int
    recipe_title: str
    total_ingredients: int
    available_count: int
    partial_count: int
    missing_count: int
    expiring_count: int
    gaps: list
    availability_score: Decimal  # 0-1, how much of the recipe is in stock
    urgency_score: Decimal  # 0-1, how urgently ingredients should be used


def analyze_recipe_gaps(recipe, household) -> GapAnalysis:
    """
    Analyze inventory gaps for a specific recipe against a household's pantry.

    Returns detailed gap analysis including availability and urgency scores.
    """
    from apps.meals.models import PantryItem, RecipeIngredient

    structured = RecipeIngredient.objects.filter(recipe=recipe).select_related("ingredient")

    if not structured.exists():
        # No structured ingredients — can't analyze
        return GapAnalysis(
            recipe_id=recipe.id,
            recipe_title=recipe.title,
            total_ingredients=0,
            available_count=0,
            partial_count=0,
            missing_count=0,
            expiring_count=0,
            gaps=[],
            availability_score=Decimal("0"),
            urgency_score=Decimal("0"),
        )

    gaps = []
    available_count = 0
    partial_count = 0
    missing_count = 0
    expiring_count = 0
    today = timezone.now().date()

    for ri in structured:
        # Look up pantry item
        pantry_item = PantryItem.objects.filter(
            household=household,
            ingredient=ri.ingredient,
        ).first()

        needed_qty = ri.quantity or Decimal("1")
        needed_unit = ri.unit

        if pantry_item is None or pantry_item.quantity <= 0:
            # Missing entirely
            gaps.append(IngredientGap(
                ingredient_id=ri.ingredient.id,
                ingredient_name=ri.ingredient.canonical_name,
                needed_quantity=needed_qty,
                needed_unit=needed_unit,
                available_quantity=Decimal("0"),
                available_unit=needed_unit,
                confidence=Decimal("1.0"),
                gap_type="missing",
            ))
            missing_count += 1
        else:
            # Check expiration
            days_until_exp = pantry_item.days_until_expiration
            is_expiring = days_until_exp is not None and 0 < days_until_exp <= 3

            # Simple quantity comparison (same unit assumed for now)
            # TODO: Cross-unit conversion in Phase 4+
            if pantry_item.unit == needed_unit:
                if pantry_item.quantity >= needed_qty:
                    gap_type = "expiring" if is_expiring else "available"
                    available_count += 1
                    if is_expiring:
                        expiring_count += 1
                else:
                    gap_type = "partial"
                    partial_count += 1
            else:
                # Different units — treat as partial with lower confidence
                gap_type = "partial"
                partial_count += 1

            gaps.append(IngredientGap(
                ingredient_id=ri.ingredient.id,
                ingredient_name=ri.ingredient.canonical_name,
                needed_quantity=needed_qty,
                needed_unit=needed_unit,
                available_quantity=pantry_item.quantity,
                available_unit=pantry_item.unit,
                confidence=pantry_item.confidence_score,
                gap_type=gap_type,
                days_until_expiration=days_until_exp,
            ))

    total = len(gaps)
    availability_score = Decimal(str(
        round(available_count / max(total, 1), 3)
    ))

    # Urgency score: higher if expiring ingredients are present
    urgency_score = Decimal("0")
    if expiring_count > 0:
        urgency_score = Decimal(str(
            round(min(expiring_count / max(total, 1) + 0.3, 1.0), 3)
        ))

    return GapAnalysis(
        recipe_id=recipe.id,
        recipe_title=recipe.title,
        total_ingredients=total,
        available_count=available_count,
        partial_count=partial_count,
        missing_count=missing_count,
        expiring_count=expiring_count,
        gaps=gaps,
        availability_score=availability_score,
        urgency_score=urgency_score,
    )


def find_pantry_expiring_soon(household, days=3):
    """
    Find all pantry items expiring within the given number of days.
    """
    from apps.meals.models import PantryItem

    cutoff = timezone.now().date() + timezone.timedelta(days=days)
    return PantryItem.objects.filter(
        household=household,
        expiration_date_estimated__lte=cutoff,
        expiration_date_estimated__gte=timezone.now().date(),
        quantity__gt=0,
    ).select_related("ingredient").order_by("expiration_date_estimated")


def decay_all_pantry_confidence(household):
    """
    Apply confidence decay to all pantry items for a household.
    Called periodically (e.g., daily) to reduce confidence over time.
    """
    from apps.meals.models import PantryItem

    items = PantryItem.objects.filter(
        household=household,
        quantity__gt=0,
    )
    updated = []
    for item in items:
        old_confidence = item.confidence_score
        item.decay_confidence()
        if item.confidence_score != old_confidence:
            updated.append(item)

    if updated:
        PantryItem.objects.bulk_update(updated, ["confidence_score"])
        logger.info(
            f"Decayed confidence for {len(updated)} pantry items "
            f"in household {household.id}"
        )
    return len(updated)
