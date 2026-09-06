"""
EXACT-IDENTITY FOOD CORRECTION (update) — the write half of nutrition correction.

WHY THIS EXISTS (production 2026-09-05). The CoS could CREATE a food entry but could not
address, update, or delete a specific existing one. Asked to "fix the Roast Beef", its only
write tool was another `log_food`, so it created a DUPLICATE; asked to remove the duplicate,
it had no reachable id and narrated "I'll do it now" without ever executing. Removal already
had a certified home (`record_correction.remove_record`, the platform's single delete
authority); UPDATE did not — and it is deliberately NOT `record_correction`'s job, whose
governing rule is "NO REPLACEMENT TRUTH". An update DOES write a replacement, but a
LEGITIMATE one: the value the user just supplied. This module owns exactly that.

GOVERNING INVARIANTS:
  * EXACT IDENTITY — updates the row whose pk is given, ownership-scoped, or fails closed.
    Never "the most recent one", never a name/description match.
  * CANONICAL CALCULATION — totals are recomputed ONLY through FoodEntry.calculate_totals()
    (per-serving snapshot × quantity, applied exactly once). This module never multiplies
    by quantity itself.
  * HONEST PROVENANCE — a value the user states is `user_override`; a value they asked WLJ
    to estimate is `ai_guess` with a moderate confidence. An estimate is never stored as a
    measurement.
  * VERIFIED POSTCONDITION — re-reads the row after the write and reports the new state, so
    the audit establishes old record -> action -> result.
"""
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

OK = "ok"
NOT_FOUND = "not_found"
NOTHING_TO_CHANGE = "nothing_to_change"
ERROR = "error"

# Tool param name -> per-serving snapshot key. (Snapshot keys match param names except
# nothing special here; kept explicit so the write surface is auditable.)
_NUTRIENT_PARAMS = (
    "calories", "protein_g", "carbohydrates_g", "fiber_g", "sugar_g",
    "fat_g", "saturated_fat_g", "sodium_mg", "cholesterol_mg", "potassium_mg",
)


def _fetch(user, entry_id):
    """Ownership-scoped fetch of an ACTIVE FoodEntry by exact pk (never a name match)."""
    from apps.health.models import FoodEntry
    if entry_id in (None, "", 0):
        return None
    return FoodEntry.objects.filter(user=user, pk=entry_id, status="active").first()


def _describe(entry):
    from apps.ai.cos_services import record_correction as _rc
    return _rc._describe_food(entry)


def describe_target(user, entry_id):
    """The deterministic CURRENT state of the exact food entry, for the confirmation."""
    entry = _fetch(user, entry_id)
    if entry is None:
        return {"status": NOT_FOUND, "record_id": entry_id,
                "message": "I couldn't find that food entry to update."}
    return {"status": OK, "record_id": entry.pk, "label": "food entry",
            "description": _describe(entry), "message": _describe(entry)}


def _num(v):
    try:
        return Decimal(str(v))
    except (TypeError, ValueError, InvalidOperation):
        return None


def update_food_entry(user, entry_id, *, food_name=None, meal_type=None,
                      quantity=None, estimated=False, **nutrition):
    """Update EXACTLY the identified food entry, through canonical Nutrition calculations.

    Only the fields the caller supplies are changed; per-serving nutrition is merged into
    the immutable per-serving snapshot and the line totals are recomputed by
    `calculate_totals()`. Returns a deterministic, VERIFIED result carrying the identity
    acted on. Idempotent for identity; never guesses; never multiplies by quantity itself.
    """
    from apps.health.models import FoodEntry

    entry = _fetch(user, entry_id)
    if entry is None:
        return {"status": NOT_FOUND, "record_id": entry_id, "changed": False,
                "message": "I couldn't find that food entry to update."}

    changed_fields = set()

    # Per-serving nutrition: overlay onto the existing snapshot (the authoritative
    # per-serving source calculate_totals reads). Absent nutrients are left untouched.
    snapshot = dict(entry.snapshot_nutrients or {})
    nutrition_supplied = False
    for key in _NUTRIENT_PARAMS:
        if key not in nutrition or nutrition[key] in (None, ""):
            continue
        val = _num(nutrition[key])
        if val is None:
            continue
        snapshot[key] = float(val)
        nutrition_supplied = True

    if food_name and str(food_name).strip():
        entry.food_name = str(food_name).strip()
        changed_fields.add("food_name")
    if meal_type and str(meal_type).strip():
        entry.meal_type = str(meal_type).strip().lower()
        changed_fields.add("meal_type")
    if quantity is not None:
        q = _num(quantity)
        if q is not None and q > 0:
            entry.quantity = q
            changed_fields.add("quantity")

    if nutrition_supplied:
        entry.snapshot_nutrients = snapshot
        changed_fields.add("snapshot_nutrients")
        # PROVENANCE: user-stated values are authoritative; an explicitly requested
        # estimate is labelled as one and never travels as a measurement.
        entry.data_source_used = (FoodEntry.DATA_SOURCE_AI_GUESS if estimated
                                  else FoodEntry.DATA_SOURCE_USER_OVERRIDE)
        entry.confidence_score = Decimal("60") if estimated else Decimal("100")
        changed_fields.add("data_source_used")

    if not changed_fields:
        return {"status": NOTHING_TO_CHANGE, "record_id": entry.pk, "changed": False,
                "description": _describe(entry),
                "message": f"Nothing to change on that food entry — {_describe(entry)}."}

    # CANONICAL recompute — the ONE place quantity is applied (per-serving × quantity).
    if {"snapshot_nutrients", "quantity"} & changed_fields:
        entry.calculate_totals()

    try:
        entry.save()
    except Exception:
        logger.warning("food_correction: save failed id=%s", entry_id, exc_info=True)
        return {"status": ERROR, "record_id": entry_id, "changed": False,
                "message": "I couldn't update that food entry."}

    # VERIFIED postcondition — re-read the row the user will now see.
    fresh = _fetch(user, entry.pk)
    return {
        "status": OK, "changed": True, "record_id": entry.pk, "label": "food entry",
        "description": _describe(fresh),
        "food_name": fresh.food_name, "meal_type": fresh.meal_type,
        "quantity": float(fresh.quantity) if fresh.quantity is not None else None,
        "calories": float(fresh.total_calories) if fresh.total_calories is not None else None,
        "estimated": fresh.data_source_used == FoodEntry.DATA_SOURCE_AI_GUESS,
        "message": f"Updated that food entry — {_describe(fresh)}.",
    }
