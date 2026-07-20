# ==============================================================================
# File: apps/meals/services/pantry_availability.py
# Project: Whole Life Journey - Meal Intelligence
# Description: THE single deterministic pantry-availability authority.
# ==============================================================================
"""One read-only answer to "how much of this requirement can the pantry satisfy?"

Before this module, two surfaces answered that question with DIFFERENT logic:
  • recipe Preparation (``preparation._deduct_one``) — density-aware, via the canonical
    ``convert_between``, comparing the recipe amount against the pantry item's exact stored
    base quantity;
  • Meal Suggestions (``inventory_gap.analyze_recipe_gaps``) — a naive same-unit string
    comparison (``pantry.unit == needed_unit``) that ignored conversion and density.

That divergence let the two surfaces DISAGREE on "can I make this tonight?" for identical
pantry state (a gram recipe vs a ml/container pantry item scored "partial" by Suggestions
but fully deducted by Preparation). This module removes the CLASS: both surfaces now call
``get_pantry_availability`` so their availability truth can never drift again.

Storage model (post Remaining-Truth refinement): ``PantryItem.quantity`` holds the EXACT
remaining amount in ``PantryItem.unit`` (ml/g/count for container items; the native unit
otherwise). ``net_content`` is the full-container size and is PRESENTATION-ONLY — it is not
part of availability arithmetic. Availability is therefore a single deterministic step:
convert the requirement into ``pantry.unit`` (using the ingredient's density for mass<->volume)
and compare against ``pantry.quantity``.

This module is READ-ONLY — it never mutates the pantry (deduction stays with the canonical
writer ``deduct_pantry_item``). No estimation: when a conversion is genuinely impossible it
returns NEEDS_INFO so callers fail closed.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from apps.meals.services.unit_conversion import convert_between

# Availability verdicts (deterministic; the model interprets, WLJ never renders a verdict).
AVAIL_FULL = "available"          # enough stock to fully satisfy the requirement
AVAIL_PARTIAL = "partial"         # some stock, but not enough
AVAIL_NONE = "none"               # no pantry item, or zero stock
AVAIL_NEEDS_INFO = "needs_info"   # cannot convert the requirement into the pantry's unit


@dataclass
class PantryAvailability:
    """The result of resolving one requirement against one pantry item — read-only."""
    status: str
    required_base: Optional[Decimal]   # requirement expressed in ``base_unit``
    usable_base: Optional[Decimal]     # available stock expressed in ``base_unit``
    base_unit: str                     # the common comparison unit (the pantry item's unit)
    deduct_amount: Optional[Decimal]   # amount to subtract from pantry_item.quantity (base_unit)
    has_container_truth: bool          # True when the item carries net_content Container Truth

    @property
    def is_available(self) -> bool:
        return self.status == AVAIL_FULL


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def get_pantry_availability(pantry_item, required_qty, required_unit,
                            density=None) -> PantryAvailability:
    """Resolve how much of ``required_qty`` ``required_unit`` the given pantry item can
    satisfy — the single availability authority both Preparation and Suggestions consume.

    ``pantry_item`` may be None (nothing on hand). ``density`` defaults to the ingredient's
    ``density_g_per_ml`` (needed for mass<->volume bridging). Never mutates anything.
    """
    required_qty = _dec(required_qty)
    if required_qty is None:
        required_qty = Decimal("1")
    req_unit = required_unit or "piece"

    if pantry_item is None:
        return PantryAvailability(AVAIL_NONE, required_qty, Decimal("0"),
                                  req_unit, None, False)

    has_container = bool(pantry_item.net_content and pantry_item.net_content_unit)
    base_unit = pantry_item.unit
    if density is None:
        density = getattr(getattr(pantry_item, "ingredient", None), "density_g_per_ml", None)

    # Convert the recipe requirement into the pantry item's stored unit. This is the SAME
    # call preparation deducts with; if it can't be bridged, fail closed (NEEDS_INFO) — the
    # caller distinguishes "missing density" vs "missing net contents" via has_container_truth.
    amount = convert_between(required_qty, req_unit, base_unit, density)
    if amount is None:
        return PantryAvailability(AVAIL_NEEDS_INFO, None, None, base_unit, None, has_container)

    qty = _dec(pantry_item.quantity) or Decimal("0")
    if qty <= 0:
        status = AVAIL_NONE
    elif qty >= amount:
        status = AVAIL_FULL
    else:
        status = AVAIL_PARTIAL
    return PantryAvailability(status, amount, qty, base_unit, amount, has_container)
