# ==============================================================================
# File: apps/meals/services/consumption.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2, Increment 3 — the person-scoped consumption bridge.
#   Prepared meal -> Consumption -> canonical FoodEntry (nutrition) -> Leftover reduced.
# ==============================================================================
"""Canonical consumption execution service.

``consume_meal`` records that a person ate servings of a (prepared) recipe. It:

  • creates ONE canonical ``health.FoodEntry`` (the SOLE nutrition record) whose
    totals are computed by the existing nutrition authority — recipe per-serving
    macros (from ``recipe_nutrition``) become the FoodEntry ``snapshot_nutrients``
    and ``FoodEntry.calculate_totals()`` scales them by servings via
    ``nutrition_calculator.compute_totals``. No macros are re-derived here;
  • automatically reduces the preparation's Leftover (floored at 0) — supporting
    multiple consumptions from one preparation (Prepared 8 → eat 2 → remaining 6);
  • emits the canonical ``health.nutrition.logged`` event so health/SAE truth
    updates exactly as any other intake log (Capture Once, Reuse Everywhere);
  • is idempotent (same key replays; never double-logs / double-reduces) and
    fail-closed (FoodEntry + leftover reduction + consumption record are atomic).

Waste / discard of leftovers is intentionally OUT of scope (the model leaves room
for it: a future WasteEvent reduces Leftover the same way, without touching this).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.meals.models import Leftover, MealConsumption, PreparationEvent


@dataclass
class ConsumptionResult:
    status: str  # "ok" | "replayed" | "failed"
    consumption_id: Optional[int] = None
    food_entry_id: Optional[int] = None
    servings_consumed: Optional[float] = None
    leftover_id: Optional[int] = None
    leftover_remaining: Optional[float] = None
    nutrition: dict = field(default_factory=dict)
    message: str = ""


def _dec(v):
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _replay(existing: MealConsumption) -> ConsumptionResult:
    entry = existing.food_entry
    return ConsumptionResult(
        status="replayed",
        consumption_id=existing.pk,
        food_entry_id=entry.pk if entry else None,
        servings_consumed=float(existing.servings_consumed),
        leftover_id=existing.leftover_id,
        leftover_remaining=(float(existing.leftover.servings)
                            if existing.leftover_id and existing.leftover else None),
        nutrition=({"calories": float(entry.total_calories),
                    "protein_g": float(entry.total_protein_g),
                    "carbohydrates_g": float(entry.total_carbohydrates_g),
                    "fat_g": float(entry.total_fat_g)} if entry else {}),
        message="replay: idempotency_key already consumed",
    )


def _emit_nutrition_logged(user, entry) -> None:
    """Emit the canonical health.nutrition.logged event (same as every other intake
    log). Fail-soft — never raises."""
    try:
        from apps.core.events.domain_events import EventTypes, safe_emit_event
        safe_emit_event(
            EventTypes.HEALTH_NUTRITION_LOGGED,
            user=user,
            data={"entry_id": getattr(entry, "pk", None), "source": "preparation"},
            source="apps.meals.services.consumption",
        )
    except Exception:  # pragma: no cover
        pass


def consume_meal(*, user, household, preparation=None, leftover=None, recipe=None,
                 servings, meal_type=None, logged_date=None, consumed_at=None,
                 idempotency_key=None, notes=""):
    """Record eating ``servings`` of a (prepared) recipe. See module docstring."""
    if idempotency_key:
        existing = MealConsumption.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return _replay(existing)

    # Resolve leftover + recipe from the preparation when not given explicitly.
    if leftover is None and preparation is not None:
        leftover = preparation.leftovers.first()
    if recipe is None:
        recipe = (getattr(preparation, "recipe", None)
                  or getattr(leftover, "recipe", None))
    if recipe is None:
        return ConsumptionResult(status="failed", message="recipe_required")

    servings = _dec(servings)
    if servings is None or servings <= 0:
        return ConsumptionResult(status="failed", message="servings_required")

    # Nutrition: reuse the recipe-nutrition authority for per-serving macros.
    from apps.meals.services.recipe_nutrition import calculate_recipe_nutrition
    per_serving = calculate_recipe_nutrition(recipe, use_cache=False).per_serving or {}
    snapshot = {k: float(v) for k, v in per_serving.items()}

    from apps.health.models import FoodEntry
    when = consumed_at or timezone.now()
    logged_date = logged_date or when.date()

    try:
        with transaction.atomic():
            entry = FoodEntry(
                user=user,
                food_name=(recipe.title or "Home-cooked meal"),
                logged_date=logged_date,
                logged_time=when.time(),
                meal_type=meal_type or FoodEntry.MEAL_DINNER,
                quantity=servings,
                serving_size=Decimal("1"),
                serving_unit="serving",
                location="home",
                entry_source="manual",
                snapshot_nutrients=snapshot,
                notes=(notes or "")[:500],
            )
            # THE authority: total_* = snapshot_per_serving * quantity (nutrition_calculator).
            entry.calculate_totals()
            entry.save()

            leftover_remaining = None
            if leftover is not None:
                current = leftover.servings or Decimal("0")
                leftover.servings = max(Decimal("0"), current - servings)
                leftover.save(update_fields=["servings", "updated_at"])
                leftover_remaining = float(leftover.servings)

            consumption = MealConsumption.objects.create(
                user=user, household=household,
                preparation=preparation, leftover=leftover, recipe=recipe,
                recipe_title=(recipe.title or ""),
                food_entry=entry, servings_consumed=servings,
                meal_type=(meal_type or ""), consumed_at=when,
                idempotency_key=idempotency_key or None,
            )
    except IntegrityError:
        if idempotency_key:
            existing = MealConsumption.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return _replay(existing)
        raise

    transaction.on_commit(lambda: _emit_nutrition_logged(user, entry))

    return ConsumptionResult(
        status="ok",
        consumption_id=consumption.pk,
        food_entry_id=entry.pk,
        servings_consumed=float(servings),
        leftover_id=(leftover.pk if leftover else None),
        leftover_remaining=leftover_remaining,
        nutrition={
            "calories": float(entry.total_calories),
            "protein_g": float(entry.total_protein_g),
            "carbohydrates_g": float(entry.total_carbohydrates_g),
            "fat_g": float(entry.total_fat_g),
        },
    )
