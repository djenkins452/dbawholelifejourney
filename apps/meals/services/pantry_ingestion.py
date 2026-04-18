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

    return pantry_item, created
