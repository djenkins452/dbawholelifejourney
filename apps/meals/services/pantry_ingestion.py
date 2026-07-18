"""
Canonical pantry ingestion finalize helper.

All user-facing ingestion entry points — receipts, barcode scans, and
pantry photo scans — ultimately need to do the same write: create or
update a PantryItem for a household+ingredient, accumulate quantity on
existing rows, set an estimated expiration for brand-new rows, and log
an InventoryTransaction for the audit trail.

Previously each entry point duplicated this write with subtle
divergence in storage-location handling, logging shape, and update
field lists. That duplication is the architectural drift the
nutrition ingestion investigation flagged.

This module is NOT a new pipeline. It is a thin, deterministic
finalize step that all three existing entry points call. It does NOT
resolve ingredients, classify storage, parse receipts, or run vision
detection — those remain the responsibility of the calling path, as
they always have. Keeping ingestion semantics in the caller preserves
existing UX while removing write-path divergence.

Contract:
    finalize_pantry_item(
        household=..., ingredient=..., quantity=...,
        source="receipt" | "barcode" | "photo_scan",
        notes="...",
        unit="piece", confidence_score=0.95,
        storage_location=None | "pantry" | "fridge" | ...,
    ) -> (PantryItem, created)

The helper guarantees:
    - quantity accumulation on existing rows
    - confidence_score and last_confirmed_at refresh on every call
    - storage_location upgrade ONLY when caller provides a non-"unknown"
      value AND the existing item's location is "unknown"
    - expiration_date_estimated set on create (if shelf_life_days known)
    - InventoryTransaction row logged for every call
    - exactly ONE domain event emitted per call:
      `meals.pantry.item_created` on create,
      `meals.pantry.item_updated` on update.

Signal consistency contract
---------------------------
Prior to this helper, the three ingestion entry points (receipt,
barcode, photo scan) emitted ZERO events — CoS and SAE had no
real-time visibility into pantry mutations. The event emission here
is the single canonical signal point for ownership changes, keeping
CoS/SAE invalidation consistent regardless of how the item was
added. Payload shape is identical across all sources (the only
difference is the `source` field).

This is OWNERSHIP emission only. Nutrition INTAKE still flows through
`health.nutrition.logged` via `FoodEntry` — we deliberately do not
emit intake signals here because buying food is not eating it.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Tuple

from django.db import transaction
from django.utils import timezone

from apps.meals.models import InventoryTransaction, PantryItem

logger = logging.getLogger(__name__)

_UNKNOWN_STORAGE = "unknown"

# Units that denote WHOLE containers on acquisition (a "piece" of ketchup = one bottle).
_CONTAINER_UNITS = {
    "piece", "pieces", "each", "unit", "units", "ct", "count", "container",
    "bottle", "jar", "can", "bag", "box", "carton", "package", "pkg", "tub",
}


def _acquire_base_amount(quantity, unit, net_content, base_unit, density):
    """Convert an acquired amount into the base unit for storage as exact Remaining Truth.

    A count/container acquisition ("1 piece", "2 bottles") means that many WHOLE
    containers → quantity × net_content. A measured acquisition ("500 ml") converts
    directly. If it cannot be converted, fall back to treating it as whole containers.
    Deterministic; no estimation.
    """
    from apps.meals.services.unit_conversion import convert_between

    u = (unit or "").strip().lower()
    if u in _CONTAINER_UNITS or not u:
        return quantity * net_content
    conv = convert_between(quantity, unit, base_unit, density)
    if conv is not None:
        return conv
    return quantity * net_content


@transaction.atomic
def finalize_pantry_item(
    *,
    household,
    ingredient,
    quantity: Decimal,
    source: str,
    notes: str,
    unit: str = "piece",
    confidence_score: Decimal = Decimal("0.95"),
    storage_location: Optional[str] = None,
) -> Tuple[PantryItem, bool]:
    """
    Canonical write for pantry ingestion.

    Returns (pantry_item, created).

    See module docstring for contract details.
    """
    if quantity is None:
        quantity = Decimal("1")
    if not isinstance(quantity, Decimal):
        quantity = Decimal(str(quantity))
    if not isinstance(confidence_score, Decimal):
        confidence_score = Decimal(str(confidence_score))

    # Resolve Container Truth (net contents of one full container) up front so this
    # acquisition can be stored as an EXACT base quantity (Remaining Truth), never as a
    # container fraction. Acquisition-independent + idempotent; best-effort, never blocks.
    net_content = None
    net_content_unit = ""
    try:
        from apps.meals.services.container_truth import resolve_net_content
        net_content, net_content_unit = resolve_net_content(ingredient)
    except Exception:  # pragma: no cover — resolution is best-effort, never blocks ingest
        logger.warning("container-truth resolution failed for ingredient %s",
                       getattr(ingredient, "pk", None), exc_info=True)
        net_content, net_content_unit = None, ""

    # Normalize the incoming amount to the canonical stored representation.
    #   Container truth known -> store the exact base quantity (containers × net_content),
    #                            unit == base unit (e.g. "ml"); percentages/fractions
    #                            are derived at presentation, never stored.
    #   No container truth     -> store as-is (legacy, fully backward-compatible).
    if net_content and net_content > 0 and net_content_unit:
        add_amount = _acquire_base_amount(
            quantity, unit, net_content, net_content_unit,
            getattr(ingredient, "density_g_per_ml", None))
        store_unit = net_content_unit
    else:
        add_amount = quantity
        store_unit = unit

    defaults = {
        "quantity": add_amount,
        "unit": store_unit,
        "confidence_score": confidence_score,
        "last_confirmed_at": timezone.now(),
    }
    if net_content and net_content > 0 and net_content_unit:
        defaults["net_content"] = net_content
        defaults["net_content_unit"] = net_content_unit
    if storage_location:
        defaults["storage_location"] = storage_location

    pantry_item, created = PantryItem.objects.get_or_create(
        household=household,
        ingredient=ingredient,
        defaults=defaults,
    )

    if created:
        # New row — set estimated expiration from shelf_life_days if known.
        if getattr(ingredient, "shelf_life_days", None):
            pantry_item.expiration_date_estimated = (
                timezone.now().date()
                + timedelta(days=ingredient.shelf_life_days)
            )
            pantry_item.save(update_fields=["expiration_date_estimated"])
    else:
        # Existing row — reconcile representation, then accumulate in the stored unit.
        update_fields = ["quantity", "confidence_score", "last_confirmed_at", "updated_at"]
        # Backfill container truth onto a pre-existing row that lacked it, converting its
        # stored quantity from containers to the exact base quantity in one deterministic
        # step (mirrors the data migration for rows written before this refinement).
        if (net_content and net_content > 0 and net_content_unit
                and pantry_item.net_content is None):
            pantry_item.quantity = (pantry_item.quantity or Decimal("0")) * net_content
            pantry_item.net_content = net_content
            pantry_item.net_content_unit = net_content_unit
            pantry_item.unit = net_content_unit
            update_fields += ["net_content", "net_content_unit", "unit"]
        pantry_item.quantity = (pantry_item.quantity or Decimal("0")) + add_amount
        pantry_item.confidence_score = confidence_score
        pantry_item.last_confirmed_at = timezone.now()
        # Upgrade storage_location only when the existing row is "unknown"
        # AND the caller provided a better value. Never downgrade.
        if (
            storage_location
            and storage_location != _UNKNOWN_STORAGE
            and pantry_item.storage_location == _UNKNOWN_STORAGE
        ):
            pantry_item.storage_location = storage_location
            update_fields.append("storage_location")
        pantry_item.save(update_fields=update_fields)

    # Audit trail — every ingestion event is logged, in the stored (base) unit so the
    # ledger folds back to `quantity` exactly.
    InventoryTransaction.objects.create(
        pantry_item=pantry_item,
        delta_quantity=add_amount,
        source=source,
        notes=notes,
    )

    logger.info(
        "Pantry finalize: household=%s ingredient=%s source=%s created=%s qty=%s",
        getattr(household, "pk", None),
        getattr(ingredient, "pk", None),
        source,
        created,
        quantity,
    )

    # Canonical signal emission — exactly one event per call, identical
    # payload shape regardless of ingestion source. Uses the existing
    # safe_emit_event() bus (apps.core.events.domain_events), which
    # provides idempotency, loop-protection, and exception isolation.
    # Emits transaction.on_commit so CoS/SAE invalidation only runs
    # after the DB write is durable — prevents stale reads on rollback.
    transaction.on_commit(
        lambda: _emit_pantry_event(
            pantry_item=pantry_item,
            ingredient=ingredient,
            household=household,
            source=source,
            quantity=add_amount,
            unit=store_unit,
            created=created,
        )
    )

    return pantry_item, created


def deduct_pantry_item(
    *,
    pantry_item: PantryItem,
    amount: Decimal,
    source: str,
    notes: str,
    preparation=None,
) -> Decimal:
    """Canonical pantry DEDUCTION authority (Foundation 2).

    Subtracts ``amount`` (already expressed in the pantry item's own unit) from
    stock, floored at 0, and logs the signed InventoryTransaction. Pantry quantity
    is NEVER mutated outside this function (or finalize_pantry_item for adds).
    Returns the amount actually deducted — less than ``amount`` when stock was short.
    """
    if amount is None:
        return Decimal("0")
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    if amount <= 0:
        return Decimal("0")

    available = pantry_item.quantity or Decimal("0")
    deducted = min(amount, available)
    if deducted <= 0:
        return Decimal("0")

    pantry_item.quantity = available - deducted
    pantry_item.save(update_fields=["quantity", "updated_at"])

    InventoryTransaction.objects.create(
        pantry_item=pantry_item,
        delta_quantity=-deducted,
        source=source,
        notes=(notes or "")[:200],
        preparation=preparation,
    )

    transaction.on_commit(
        lambda: _emit_pantry_event(
            pantry_item=pantry_item,
            ingredient=pantry_item.ingredient,
            household=pantry_item.household,
            source=source,
            quantity=-deducted,
            unit=pantry_item.unit,
            created=False,
        )
    )
    return deducted


def _emit_pantry_event(
    *,
    pantry_item: PantryItem,
    ingredient,
    household,
    source: str,
    quantity: Decimal,
    unit: str,
    created: bool,
) -> None:
    """
    Emit the canonical pantry domain event.

    Separated from finalize_pantry_item() so it can be invoked from
    `transaction.on_commit` without capturing the entire helper's
    closure. Keep this function fail-soft — signal emission must
    never block or raise from the primary write path, and
    `safe_emit_event` already guarantees that.
    """
    try:
        from apps.core.events.domain_events import (
            EventTypes,
            safe_emit_event,
        )
    except Exception as e:  # pragma: no cover — extremely defensive
        logger.warning(
            "Pantry event bus unavailable; skipping emission: %s", e
        )
        return

    event_type = (
        EventTypes.MEALS_PANTRY_ITEM_CREATED
        if created
        else EventTypes.MEALS_PANTRY_ITEM_UPDATED
    )
    user = getattr(household, "primary_user", None)

    safe_emit_event(
        event_type,
        user=user,
        data={
            "household_id": getattr(household, "pk", None),
            "pantry_item_id": getattr(pantry_item, "pk", None),
            "ingredient_id": getattr(ingredient, "pk", None),
            "ingredient_name": getattr(ingredient, "canonical_name", None)
            or getattr(ingredient, "name", None),
            "quantity_delta": float(quantity) if quantity is not None else 0.0,
            "unit": unit,
            "storage_location": getattr(pantry_item, "storage_location", None),
            "source": source,
            "created": created,
        },
        source="apps.meals.services.pantry_ingestion",
    )
