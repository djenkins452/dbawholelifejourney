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

    defaults = {
        "quantity": quantity,
        "unit": unit,
        "confidence_score": confidence_score,
        "last_confirmed_at": timezone.now(),
    }
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
        # Existing row — accumulate quantity and refresh confidence/last-seen.
        pantry_item.quantity = (pantry_item.quantity or Decimal("0")) + quantity
        pantry_item.confidence_score = confidence_score
        pantry_item.last_confirmed_at = timezone.now()
        update_fields = [
            "quantity",
            "confidence_score",
            "last_confirmed_at",
            "updated_at",
        ]
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

    # Audit trail — every ingestion event is logged.
    InventoryTransaction.objects.create(
        pantry_item=pantry_item,
        delta_quantity=quantity,
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
            quantity=quantity,
            unit=unit,
            created=created,
        )
    )

    return pantry_item, created


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
