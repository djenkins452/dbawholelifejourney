"""
Substitution Engine

Provides intelligent ingredient substitutions for:
- Diabetes-aware low-carb swaps
- Allergy/dietary flag compliance
- Pantry-based "use what you have" suggestions
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Substitution:
    """A suggested ingredient substitution."""
    original_ingredient_id: int
    original_name: str
    substitute_ingredient_id: int
    substitute_name: str
    reason: str
    confidence: Decimal
    carb_savings_g: Optional[Decimal] = None
    is_in_pantry: bool = False


def find_substitutions(
    ingredient,
    household=None,
    dietary_profile=None,
    max_results=3,
) -> list[Substitution]:
    """
    Find substitutions for an ingredient.

    Priority order:
    1. Explicit low_carb_alternative (if diabetes-sensitive)
    2. Same substitution_group ingredients in pantry
    3. Same category ingredients in pantry
    """
    from apps.meals.models import Ingredient, PantryItem

    substitutions = []

    # 1. Explicit low-carb alternative
    if (
        dietary_profile
        and dietary_profile.diabetes_sensitive
        and ingredient.low_carb_alternative
    ):
        alt = ingredient.low_carb_alternative
        carb_savings = max(
            Decimal("0"),
            ingredient.carb_density - alt.carb_density,
        )
        is_in_pantry = False
        if household:
            is_in_pantry = PantryItem.objects.filter(
                household=household,
                ingredient=alt,
                quantity__gt=0,
            ).exists()

        substitutions.append(Substitution(
            original_ingredient_id=ingredient.id,
            original_name=ingredient.canonical_name,
            substitute_ingredient_id=alt.id,
            substitute_name=alt.canonical_name,
            reason=f"Low-carb alternative (saves ~{carb_savings}g carbs per 100g)",
            confidence=Decimal("0.90"),
            carb_savings_g=carb_savings,
            is_in_pantry=is_in_pantry,
        ))

    # 2. Same substitution group (in pantry first)
    if ingredient.substitution_group and household:
        group_items = Ingredient.objects.filter(
            substitution_group=ingredient.substitution_group,
        ).exclude(pk=ingredient.pk)

        for alt in group_items[:5]:
            in_pantry = PantryItem.objects.filter(
                household=household,
                ingredient=alt,
                quantity__gt=0,
            ).exists()

            if in_pantry:
                substitutions.append(Substitution(
                    original_ingredient_id=ingredient.id,
                    original_name=ingredient.canonical_name,
                    substitute_ingredient_id=alt.id,
                    substitute_name=alt.canonical_name,
                    reason=f"In your pantry, same group ({ingredient.substitution_group})",
                    confidence=Decimal("0.80"),
                    is_in_pantry=True,
                ))

    # 3. Same category (in pantry, lower priority)
    if household and len(substitutions) < max_results:
        same_category = Ingredient.objects.filter(
            category=ingredient.category,
        ).exclude(
            pk=ingredient.pk,
        ).exclude(
            pk__in=[s.substitute_ingredient_id for s in substitutions],
        )

        for alt in same_category[:3]:
            in_pantry = PantryItem.objects.filter(
                household=household,
                ingredient=alt,
                quantity__gt=0,
            ).exists()

            if in_pantry:
                substitutions.append(Substitution(
                    original_ingredient_id=ingredient.id,
                    original_name=ingredient.canonical_name,
                    substitute_ingredient_id=alt.id,
                    substitute_name=alt.canonical_name,
                    reason=f"In your pantry, same category ({ingredient.category})",
                    confidence=Decimal("0.60"),
                    is_in_pantry=True,
                ))

    return substitutions[:max_results]
