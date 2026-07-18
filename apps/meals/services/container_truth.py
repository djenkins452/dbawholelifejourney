# ==============================================================================
# File: apps/meals/services/container_truth.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Deterministic Pantry Container Truth resolution (Foundation 2).
# ==============================================================================
"""Resolve a pantry item's Container Truth — the net contents of ONE container in a
base unit (g / ml / count) — deterministically, in priority order:

  1. FoodItem.net_content          (from the Open Food Facts product_quantity)
  2. FoodItem serving_size × servings_per_container
  3. Ingredient default_quantity / default_unit  (canonical per-ingredient default)
  4. None  →  the one fact we must ask the user for once

Acquisition-independent: barcode / receipt / vision / manual all flow through this
same resolver (via finalize_pantry_item), so the acquisition method never changes the
stored truth. No estimation — every source is a stored deterministic value.
"""
from decimal import Decimal

from apps.meals.services.unit_conversion import base_unit_for, convert_between


def _d(v):
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def resolve_net_content(ingredient, food_item=None):
    """Return (net_content: Decimal, base_unit: str) for one container of this
    ingredient, or (None, "") when no deterministic source exists (→ ask the user)."""
    from apps.meals.models import Ingredient

    base = ingredient.base_measure
    base_unit = base_unit_for(base)
    density = ingredient.density_g_per_ml

    # COUNT substances need no container bridge — the legacy unit-matching path already
    # deducts count↔count correctly. Returning None here keeps every count-default
    # (i.e. unseeded) ingredient on that path, so weight/volume items that simply haven't
    # been given a base_measure yet are never wrongly forced through the container path.
    if base == Ingredient.MEASURE_COUNT:
        return (None, "")

    fi = food_item or getattr(ingredient, "nutrition_source", None)

    # 1. FoodItem.net_content (Open Food Facts product_quantity).
    if fi is not None and _d(fi.net_content) and fi.net_content_unit:
        c = convert_between(_d(fi.net_content), fi.net_content_unit, base_unit, density)
        if c and c > 0:
            return (round(c, 3), base_unit)

    # 2. FoodItem serving_size × servings_per_container.
    if fi is not None and _d(fi.serving_size) and _d(fi.servings_per_container):
        total = _d(fi.serving_size) * _d(fi.servings_per_container)
        c = convert_between(total, fi.serving_unit or base_unit, base_unit, density)
        if c and c > 0:
            return (round(c, 3), base_unit)

    # 3. Ingredient default (a canonical typical package for this ingredient).
    if _d(ingredient.default_quantity) and ingredient.default_unit:
        c = convert_between(_d(ingredient.default_quantity), ingredient.default_unit,
                            base_unit, density)
        if c and c > 0:
            return (round(c, 3), base_unit)

    # 4. Unknown — the missing fact the user provides once.
    return (None, "")


def set_container_truth(pantry_item, net_content, net_content_unit, *,
                        container_type="", save=True):
    """Apply Container Truth to a PantryItem and normalize its Remaining Truth to an EXACT
    base quantity in one deterministic step.

    Used by the in-workflow capture ("what size bottle is this?"). If the item's remaining
    quantity is currently expressed as containers/pieces (its unit is not the base unit),
    it is converted to the base quantity (quantity × net_content) so stored truth becomes
    exact; a quantity already in the base unit is left untouched. Returns the pantry_item.
    """
    net = _d(net_content)
    if net is None or net <= 0 or not net_content_unit:
        return pantry_item

    fields = ["net_content", "net_content_unit", "updated_at"]
    if pantry_item.unit != net_content_unit:
        # Currently "N containers" → store the exact base quantity.
        pantry_item.quantity = (pantry_item.quantity or Decimal("0")) * net
        pantry_item.unit = net_content_unit
        fields.append("quantity")
        fields.append("unit")
    pantry_item.net_content = net
    pantry_item.net_content_unit = net_content_unit
    if container_type:
        pantry_item.container_type = container_type
        fields.append("container_type")
    if save:
        pantry_item.save(update_fields=fields)
    return pantry_item
