# ==============================================================================
# File: apps/meals/services/leftover_queries.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Canonical leftover query authority (Foundation 2, Increment 4).
# ==============================================================================
"""Deterministic reads over the household leftover inventory.

The SINGLE source of "what leftovers do I have". Only truly-available leftovers
(active + disposition AVAILABLE + servings > 0) are surfaced; consumed / discarded /
expired / soft-deleted rows are excluded. Facts only — no verdicts.
"""
from decimal import Decimal

from apps.meals.models import Leftover


def available_leftovers(household):
    """Available leftovers for a household (newest first). Household-isolated."""
    return (
        Leftover.objects.filter(
            household=household,
            status="active",
            disposition=Leftover.DISP_AVAILABLE,
            servings__gt=0,
        )
        .select_related("recipe", "preparation")
        .order_by("-created_at")
    )


def leftover_summary(household):
    """Facts-only deterministic summary of available leftovers (page render + the
    meals.leftovers Current Context provider read from THIS one source)."""
    rows = list(available_leftovers(household))
    total = sum((lo.servings or Decimal("0") for lo in rows), Decimal("0"))
    items = [
        {
            "id": lo.pk,
            "recipe_title": lo.recipe_title or (lo.recipe.title if lo.recipe else "a meal"),
            "servings": float(lo.servings),
            "prepared_date": (lo.preparation.prepared_at.date().isoformat()
                              if lo.preparation and lo.preparation.prepared_at else None),
            "expiration_date": lo.expiration_date.isoformat() if lo.expiration_date else None,
        }
        for lo in rows
    ]
    return {
        "count": len(rows),
        "total_servings": float(total),
        "items": items,
    }
