"""
Ingredient Matching Service

Thin compatibility layer over the canonical Ingredient Intelligence authority
(``apps.meals.services.ingredient_intelligence``). Both resolvers below are now fully
DETERMINISTIC (exact canonical → explicit alias → normalized identity key) — the previous
fuzzy substring/Jaccard matching has been removed, per the Ingredient Intelligence contract:
no fuzzy, no AI, in any production resolution; every relationship is explainable.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class IngredientMatch:
    """Result of matching a parsed name to a canonical Ingredient."""
    ingredient_id: Optional[int]
    canonical_name: str
    confidence: Decimal
    match_method: str  # "exact", "alias", "normalized", "none"


def match_ingredient_name(name: str) -> IngredientMatch:
    """Deterministically link a parsed name to a canonical Ingredient WITHOUT creating one.

    Delegates to the canonical resolver (read-only). Returns ``ingredient_id=None`` /
    ``match_method="none"`` when there is no deterministic match — honest, never a fuzzy guess.
    """
    from apps.meals.services.ingredient_intelligence import resolve_ingredient

    if not name:
        return IngredientMatch(None, "", Decimal("0"), "none")

    name_lower = name.lower().strip()
    ing = resolve_ingredient(name, create=False)
    if ing is None:
        return IngredientMatch(None, name, Decimal("0"), "none")

    # Classify how it matched (for reporting/confidence), deterministically.
    if (ing.canonical_name or "").lower() == name_lower:
        method, confidence = "exact", Decimal("1.0")
    elif name_lower in (a.lower() for a in (ing.aliases or [])):
        method, confidence = "alias", Decimal("1.0")
    else:
        method, confidence = "normalized", Decimal("0.95")
    return IngredientMatch(ing.id, ing.canonical_name, confidence, method)


def get_or_create_ingredient(name: str, category: str = "other") -> "Ingredient":
    """Resolve a name to its canonical Ingredient, creating one only if none exists.

    The single row-creating seam for every acquisition path (recipe enrichment, manual entry,
    barcode, receipt, vision). Delegates to the canonical resolver so all paths converge on
    one identity per real ingredient and surface-form variants are recorded as aliases.
    """
    from apps.meals.services.ingredient_intelligence import resolve_ingredient

    return resolve_ingredient(name, category=category, create=True)
