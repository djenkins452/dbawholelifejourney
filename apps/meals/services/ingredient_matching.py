"""
Ingredient Matching Service

Matches parsed ingredient names to canonical Ingredient records.
Uses deterministic matching first, then fuzzy matching, with AI fallback.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import Q

logger = logging.getLogger(__name__)


@dataclass
class IngredientMatch:
    """Result of matching a parsed name to a canonical Ingredient."""
    ingredient_id: Optional[int]
    canonical_name: str
    confidence: Decimal
    match_method: str  # "exact", "alias", "fuzzy", "ai", "none"


def match_ingredient_name(name: str) -> IngredientMatch:
    """
    Match a parsed ingredient name to a canonical Ingredient.

    Strategy (in order):
    1. Exact match on canonical_name
    2. Alias match
    3. Substring/contains match
    4. Word overlap scoring
    5. Return no match (caller can invoke AI)
    """
    from apps.meals.models import Ingredient

    if not name:
        return IngredientMatch(
            ingredient_id=None,
            canonical_name="",
            confidence=Decimal("0"),
            match_method="none",
        )

    name_lower = name.lower().strip()

    # 1. Exact canonical match
    exact = Ingredient.objects.filter(canonical_name__iexact=name_lower).first()
    if exact:
        return IngredientMatch(
            ingredient_id=exact.id,
            canonical_name=exact.canonical_name,
            confidence=Decimal("1.0"),
            match_method="exact",
        )

    # 2. Alias match — check JSON aliases field
    # Filter candidates that might contain our name in aliases
    for ingredient in Ingredient.objects.all().iterator():
        if ingredient.matches_text(name_lower):
            return IngredientMatch(
                ingredient_id=ingredient.id,
                canonical_name=ingredient.canonical_name,
                confidence=Decimal("0.95"),
                match_method="alias",
            )

    # 3. Contains match — ingredient name contains our search or vice versa
    contains_qs = Ingredient.objects.filter(
        Q(canonical_name__icontains=name_lower)
        | Q(canonical_name__in=[name_lower])
    )
    # Also check if our name contains the ingredient name
    all_ingredients = Ingredient.objects.values_list("id", "canonical_name")
    best_contains = None
    best_overlap = 0

    for ing_id, canonical in all_ingredients:
        canonical_lower = canonical.lower()
        # Our name contains the canonical name
        if canonical_lower in name_lower:
            overlap = len(canonical_lower) / max(len(name_lower), 1)
            if overlap > best_overlap:
                best_overlap = overlap
                best_contains = (ing_id, canonical)
        # Canonical contains our name
        elif name_lower in canonical_lower:
            overlap = len(name_lower) / max(len(canonical_lower), 1)
            if overlap > best_overlap:
                best_overlap = overlap
                best_contains = (ing_id, canonical)

    if best_contains and best_overlap > 0.5:
        return IngredientMatch(
            ingredient_id=best_contains[0],
            canonical_name=best_contains[1],
            confidence=Decimal(str(round(min(best_overlap + 0.2, 0.90), 2))),
            match_method="fuzzy",
        )

    # 4. Word overlap scoring
    name_words = set(name_lower.split())
    best_word_match = None
    best_word_score = 0

    for ing_id, canonical in all_ingredients:
        canonical_words = set(canonical.lower().split())
        overlap = len(name_words & canonical_words)
        total = len(name_words | canonical_words)
        if total > 0:
            score = overlap / total  # Jaccard similarity
            if score > best_word_score and score >= 0.3:
                best_word_score = score
                best_word_match = (ing_id, canonical)

    if best_word_match and best_word_score >= 0.3:
        return IngredientMatch(
            ingredient_id=best_word_match[0],
            canonical_name=best_word_match[1],
            confidence=Decimal(str(round(min(best_word_score + 0.1, 0.80), 2))),
            match_method="fuzzy",
        )

    # 5. No match found
    return IngredientMatch(
        ingredient_id=None,
        canonical_name=name,
        confidence=Decimal("0"),
        match_method="none",
    )


def get_or_create_ingredient(name: str, category: str = "other") -> "Ingredient":
    """
    Get an existing ingredient or create a new one.

    Used when the matching service can't find a match and we need
    to create a new canonical ingredient.
    """
    from apps.meals.models import Ingredient

    name_lower = name.lower().strip()

    # Try exact match first
    ingredient = Ingredient.objects.filter(canonical_name__iexact=name_lower).first()
    if ingredient:
        return ingredient

    # Create new
    ingredient = Ingredient.objects.create(
        canonical_name=name_lower,
        category=category,
    )
    logger.info(f"Created new ingredient: {name_lower} (category: {category})")
    return ingredient
