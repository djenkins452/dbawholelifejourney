# ==============================================================================
# File: apps/meals/services/preparation.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2 — the household preparation execution spine.
#   Recipe -> PreparationEvent -> inventory deduction -> leftovers.
# ==============================================================================
"""Canonical preparation execution service.

``prepare_recipe`` records that a household cooked a recipe, deducts the recipe's
structured ingredients from the pantry through the canonical InventoryTransaction
authority, and (optionally) records leftovers. It is:

  • deterministic  — every deduction is computed from RecipeIngredient + pantry;
  • fail-closed     — the whole event + deductions + leftover commit atomically, so a
                      failure leaves NO partial deduction;
  • idempotent      — a repeat with the same idempotency_key is a no-op replay (never
                      double-deducts), robust to refresh / Celery retry / replay;
  • honest          — never records false completion; preparation_status and
                      deduction_status are tracked separately, with a per-ingredient
                      audit trail in deduction_summary.

Consumption / FoodEntry / nutrition logging is intentionally OUT of scope here.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.meals.models import Leftover, PantryItem, PreparationEvent, RecipeIngredient
from apps.meals.services.pantry_ingestion import deduct_pantry_item
from apps.meals.services.unit_conversion import convert_between


# Per-ingredient deduction outcome statuses (audit vocabulary).
D_APPLIED = "applied"
D_PARTIAL = "partial"
D_SHORTAGE = "shortage"
D_UNSUPPORTED = "unsupported_conversion"
D_NEEDS_CONTAINER = "needs_container_info"
D_NO_PANTRY = "no_pantry_item"
D_NO_QUANTITY = "no_quantity"

_SHORTFALL_STATUSES = {D_PARTIAL, D_SHORTAGE, D_UNSUPPORTED, D_NEEDS_CONTAINER,
                       D_NO_PANTRY, D_NO_QUANTITY}


@dataclass
class PreparationResult:
    status: str  # "ok" | "replayed" | "failed"
    preparation_id: Optional[int] = None
    preparation_status: Optional[str] = None
    deduction_status: Optional[str] = None
    deductions: List[dict] = field(default_factory=list)
    leftover_id: Optional[int] = None
    message: str = ""


def _dec(v, default=None):
    if v is None:
        return default
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _replay(existing: PreparationEvent) -> PreparationResult:
    leftover = existing.leftovers.first()
    return PreparationResult(
        status="replayed",
        preparation_id=existing.pk,
        preparation_status=existing.preparation_status,
        deduction_status=existing.deduction_status,
        deductions=(existing.deduction_summary or {}).get("deductions", []),
        leftover_id=leftover.pk if leftover else None,
        message="replay: idempotency_key already prepared",
    )


def _deduct_one(household, ri: RecipeIngredient, scale: Decimal, prep: PreparationEvent) -> dict:
    """Deduct a single structured ingredient. Returns an audit dict; never raises for
    business shortfalls (missing pantry / bad conversion / insufficient stock)."""
    ingredient = ri.ingredient
    name = getattr(ingredient, "canonical_name", "") or ""
    req_unit = (ri.unit or "piece")
    density = getattr(ingredient, "density_g_per_ml", None)
    notes = f"Prepared {prep.recipe_title or 'recipe'}"

    required = _dec(ri.quantity)
    if required is None:
        return {"ingredient": name, "status": D_NO_QUANTITY, "required": None,
                "required_unit": req_unit, "deducted": 0.0, "note": "unquantified (to taste)"}

    required_scaled = required * scale

    pantry = (PantryItem.objects.select_for_update()
              .filter(household=household, ingredient=ingredient).first())
    if pantry is None:
        return {"ingredient": name, "status": D_NO_PANTRY, "required": float(required_scaled),
                "required_unit": req_unit, "deducted": 0.0, "note": "not in pantry"}

    # ── Container Truth path: pantry knows net contents → deduct in a base unit ──
    # remaining is tracked as fractional containers (Remaining Truth); usable base =
    # quantity × net_content. The recipe amount is converted to the base unit (with the
    # ingredient's density for mass↔volume), then expressed back as containers to deduct.
    if pantry.net_content and pantry.net_content_unit:
        base_unit = pantry.net_content_unit
        required_base = convert_between(required_scaled, req_unit, base_unit, density)
        if required_base is None:
            return {"ingredient": name, "status": D_UNSUPPORTED,
                    "required": float(required_scaled), "required_unit": req_unit,
                    "pantry_unit": base_unit, "deducted": 0.0,
                    "note": f"cannot convert {req_unit} -> {base_unit} "
                            f"(no density for {name}?)"}
        net = pantry.net_content
        usable_base = (pantry.quantity or Decimal("0")) * net
        required_containers = required_base / net
        deducted_containers = deduct_pantry_item(
            pantry_item=pantry, amount=required_containers, source="preparation",
            notes=notes, preparation=prep)
        deducted_base = deducted_containers * net
        if deducted_base >= required_base:
            status = D_APPLIED
        elif deducted_base > 0:
            status = D_PARTIAL
        else:
            status = D_SHORTAGE
        return {"ingredient": name, "status": status, "required": float(round(required_base, 3)),
                "required_unit": base_unit, "pantry_available": float(round(usable_base, 3)),
                "deducted": float(round(deducted_base, 3)), "note": ""}

    # ── No Container Truth: fall back to legacy unit-matching ──
    amount = convert_between(required_scaled, req_unit, pantry.unit, density)
    if amount is None:
        # The one missing fact is this item's net contents — ask for it once (not a
        # dead-end "unsupported_conversion").
        return {"ingredient": name, "status": D_NEEDS_CONTAINER,
                "required": float(required_scaled), "required_unit": req_unit,
                "pantry_unit": pantry.unit, "deducted": 0.0,
                "note": f"How much is one {pantry.unit or 'container'} of {name}? "
                        f"Add its net contents once and this becomes automatic."}

    available = pantry.quantity or Decimal("0")
    deducted = deduct_pantry_item(
        pantry_item=pantry, amount=amount, source="preparation",
        notes=notes, preparation=prep)

    if deducted >= amount:
        status = D_APPLIED
    elif deducted > 0:
        status = D_PARTIAL
    else:
        status = D_SHORTAGE
    return {"ingredient": name, "status": status, "required": float(amount),
            "required_unit": pantry.unit, "pantry_available": float(available),
            "deducted": float(deducted), "note": ""}


def _maybe_leftover(prep, recipe, leftover_servings, household, user) -> Optional[int]:
    servings = _dec(leftover_servings)
    if servings is None or servings <= 0:
        return None
    leftover = Leftover.objects.create(
        user=user, household=household, preparation=prep, recipe=recipe,
        recipe_title=(recipe.title if recipe else ""), servings=servings)
    return leftover.pk


def prepare_recipe(*, household, user, recipe, servings=None, leftover_servings=None,
                   idempotency_key=None, notes="", prepared_at=None) -> PreparationResult:
    """Record a preparation of ``recipe`` for ``household`` and deduct pantry stock.

    Fail-closed + idempotent. See module docstring.
    """
    # --- Idempotency: replay an already-recorded key without re-deducting ---
    if idempotency_key:
        existing = PreparationEvent.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return _replay(existing)

    if recipe is None:
        return PreparationResult(status="failed", message="recipe_required")

    recipe_servings = _dec(recipe.servings, Decimal("1")) or Decimal("1")
    if recipe_servings <= 0:
        recipe_servings = Decimal("1")
    servings_prepared = _dec(servings, recipe_servings) or recipe_servings
    scale = servings_prepared / recipe_servings

    structured = list(
        RecipeIngredient.objects.filter(recipe=recipe).select_related("ingredient")
        .order_by("order_index"))

    try:
        with transaction.atomic():
            prep = PreparationEvent.objects.create(
                user=user, household=household, recipe=recipe,
                recipe_title=recipe.title or "",
                servings_prepared=servings_prepared,
                preparation_status=PreparationEvent.PREP_COMPLETED,
                deduction_status=PreparationEvent.DED_PENDING,
                prepared_at=prepared_at or timezone.now(),
                idempotency_key=idempotency_key or None,
                notes=(notes or "")[:300],
            )

            deductions: List[dict] = []
            for ri in structured:
                deductions.append(_deduct_one(household, ri, scale, prep))

            any_applied = any(d["deducted"] > 0 for d in deductions)
            any_shortfall = any(d["status"] in _SHORTFALL_STATUSES for d in deductions)

            if not structured:
                prep.deduction_status = PreparationEvent.DED_SKIPPED
            elif any_applied and any_shortfall:
                prep.deduction_status = PreparationEvent.DED_PARTIAL
            elif any_applied:
                prep.deduction_status = PreparationEvent.DED_APPLIED
            else:
                # Structured ingredients existed but nothing could be deducted.
                prep.deduction_status = PreparationEvent.DED_SKIPPED

            prep.deduction_summary = {
                "scale": float(scale),
                "servings_prepared": float(servings_prepared),
                "recipe_servings": float(recipe_servings),
                "deductions": deductions,
            }
            prep.save(update_fields=["deduction_status", "deduction_summary", "updated_at"])

            leftover_id = _maybe_leftover(prep, recipe, leftover_servings, household, user)

    except IntegrityError:
        # Idempotency race: a concurrent request created the same key first.
        if idempotency_key:
            existing = PreparationEvent.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return _replay(existing)
        raise

    return PreparationResult(
        status="ok",
        preparation_id=prep.pk,
        preparation_status=prep.preparation_status,
        deduction_status=prep.deduction_status,
        deductions=deductions,
        leftover_id=leftover_id,
    )
