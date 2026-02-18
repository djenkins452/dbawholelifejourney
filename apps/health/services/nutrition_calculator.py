# ==============================================================================
# File: nutrition_calculator.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Authoritative nutrient math — all total calculations flow through
#              here. Server-side is source of truth; JS previews use same logic.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-17
# ==============================================================================
"""
Nutrition Calculator Service — single source of truth for nutrient math.

All nutrient total calculations MUST use this module. Do not duplicate
multiplication logic elsewhere.

Usage:
    from apps.health.services.nutrition_calculator import compute_totals, build_snapshot

    snapshot = build_snapshot(food_item)       # per-serving dict
    totals = compute_totals(snapshot, qty=2)   # all values doubled
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Union

# Canonical list of nutrient fields tracked in snapshots.
# Order matters for display consistency.
NUTRIENT_FIELDS = [
    'calories',
    'protein_g',
    'carbohydrates_g',
    'fiber_g',
    'sugar_g',
    'fat_g',
    'saturated_fat_g',
    'unsaturated_fat_g',
    'trans_fat_g',
    'sodium_mg',
    'cholesterol_mg',
    'potassium_mg',
    'calcium_mg',
    'iron_mg',
    'vitamin_a_iu',
    'vitamin_c_mg',
    'vitamin_d_iu',
    'vitamin_b12_mcg',
]

# Subset that most entries will have (the "core" macros + common micros)
CORE_NUTRIENT_FIELDS = [
    'calories',
    'protein_g',
    'carbohydrates_g',
    'fiber_g',
    'sugar_g',
    'fat_g',
    'saturated_fat_g',
    'sodium_mg',
    'cholesterol_mg',
    'potassium_mg',
]


def _to_decimal(value) -> Optional[Decimal]:
    """Safely convert a value to Decimal. Returns None if not convertible."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def build_snapshot(source, user=None) -> dict:
    """
    Build a per-serving nutrient snapshot dict from a food source.

    Checks for a user-specific FoodItemOverride first (if user provided
    and source is a FoodItem). Falls back to the source's own values.

    Args:
        source: FoodItem, CustomFood, or any object with nutrient attributes
        user: Optional user to check for FoodItemOverride

    Returns:
        Dict of {nutrient_field: float_value} for all available nutrients
    """
    # Check for user override (Phase 5 feature)
    if user and hasattr(source, 'user_overrides'):
        try:
            override = source.user_overrides.filter(
                user=user, status='active'
            ).first()
            if override and override.overridden_nutrients:
                return override.overridden_nutrients
        except Exception:
            pass  # Fall through to source values

    snapshot = {}
    for field in NUTRIENT_FIELDS:
        value = getattr(source, field, None)
        if value is not None:
            try:
                snapshot[field] = float(value)
            except (ValueError, TypeError):
                pass
    return snapshot


def compute_totals(
    snapshot_per_serving: dict,
    quantity: Union[Decimal, float, int, str],
) -> dict:
    """
    Multiply all per-serving nutrient values by quantity.

    This is THE authoritative calculation. All entry total_* fields
    must be set by calling this function.

    Args:
        snapshot_per_serving: Dict of {nutrient: per_serving_value}
        quantity: Number of servings consumed

    Returns:
        Dict of {total_nutrient: calculated_total} — keys prefixed with "total_"
    """
    qty = _to_decimal(quantity)
    if qty is None:
        qty = Decimal('1')

    totals = {}
    for key, value in snapshot_per_serving.items():
        dec_val = _to_decimal(value)
        if dec_val is not None:
            result = (dec_val * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            totals[f'total_{key}'] = float(result)
        else:
            totals[f'total_{key}'] = None

    return totals


def snapshot_from_totals(totals_dict: dict, quantity: Union[Decimal, float, int, str]) -> dict:
    """
    Reverse-compute per-serving values from stored totals and quantity.

    Used during data migration to backfill snapshot_nutrients from existing
    FoodEntry records that only have total_* fields.

    Args:
        totals_dict: Dict of {total_calories: 20, total_protein_g: 4, ...}
        quantity: Number of servings that produced those totals

    Returns:
        Dict of {calories: 10, protein_g: 2, ...} — per-serving values
    """
    qty = _to_decimal(quantity)
    if not qty or qty == 0:
        qty = Decimal('1')

    snapshot = {}
    for key, value in totals_dict.items():
        # Strip "total_" prefix
        nutrient_key = key.replace('total_', '') if key.startswith('total_') else key
        dec_val = _to_decimal(value)
        if dec_val is not None:
            result = (dec_val / qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            snapshot[nutrient_key] = float(result)
        else:
            snapshot[nutrient_key] = None

    return snapshot
