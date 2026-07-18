# ==============================================================================
# File: apps/meals/services/waste.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2, Increment 4 — leftover discard + deterministic expiration.
# ==============================================================================
"""Canonical leftover waste truth.

``discard_leftover`` records a leftover being thrown out; ``expire_due_leftovers``
deterministically expires leftovers whose TRUSTED stored expiration_date has passed.

Neither ever:
  • creates a health.FoodEntry (waste is not nutrition),
  • counts toward nutrition, or
  • touches pantry inventory (preparation already deducted the ingredients — a
    discarded prepared leftover changes leftover disposition, not pantry quantity).

Both are atomic, row-locked (no over-discard / concurrency races), and idempotent
(FoodWasteEvent.idempotency_key), and both record an immutable FoodWasteEvent audit.
Expiration NEVER invents a date — it acts only on a stored expiration_date.
"""
import logging
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.meals.models import FoodWasteEvent, Leftover

logger = logging.getLogger(__name__)


@dataclass
class WasteResult:
    status: str  # "ok" | "replayed" | "failed"
    waste_event_id: Optional[int] = None
    leftover_id: Optional[int] = None
    leftover_remaining: Optional[float] = None
    disposition: Optional[str] = None
    message: str = ""


def _dec(v):
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _replay(existing: FoodWasteEvent) -> WasteResult:
    lo = existing.leftover
    return WasteResult(
        status="replayed",
        waste_event_id=existing.pk,
        leftover_id=existing.leftover_id,
        leftover_remaining=(float(lo.servings) if lo else None),
        disposition=(lo.disposition if lo else None),
        message="replay: idempotency_key already recorded",
    )


def discard_leftover(*, user, household, leftover, servings=None, reason="",
                     occurred_at=None, idempotency_key=None,
                     source=FoodWasteEvent.SOURCE_USER) -> WasteResult:
    """Discard ``servings`` of a leftover (default: all remaining). See module docstring."""
    if idempotency_key:
        existing = FoodWasteEvent.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return _replay(existing)

    if leftover is None:
        return WasteResult(status="failed", message="leftover_required")

    try:
        with transaction.atomic():
            lo = Leftover.objects.select_for_update().filter(pk=leftover.pk).first()
            if lo is None or not lo.is_available:
                return WasteResult(status="failed", message="leftover_unavailable")

            available = lo.servings or Decimal("0")
            amount = _dec(servings) if servings is not None else available
            if amount is None or amount <= 0:
                return WasteResult(status="failed", message="servings_required")
            if amount > available:
                return WasteResult(status="failed", message="insufficient_leftover")

            event = FoodWasteEvent.objects.create(
                user=user, household=household, leftover=lo,
                preparation=lo.preparation, recipe=lo.recipe,
                recipe_title=lo.recipe_title,
                event_type=FoodWasteEvent.EVENT_DISCARDED,
                servings=amount, reason=(reason or "")[:300], source=source,
                occurred_at=occurred_at or timezone.now(),
                idempotency_key=idempotency_key or None,
            )

            remaining = available - amount
            lo.servings = remaining
            if remaining <= 0:
                lo.disposition = Leftover.DISP_DISCARDED
                lo.depleted_at = timezone.now()
                lo.save(update_fields=["servings", "disposition", "depleted_at", "updated_at"])
            else:
                lo.save(update_fields=["servings", "updated_at"])
    except IntegrityError:
        if idempotency_key:
            existing = FoodWasteEvent.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return _replay(existing)
        raise

    return WasteResult(status="ok", waste_event_id=event.pk, leftover_id=lo.pk,
                       leftover_remaining=float(lo.servings), disposition=lo.disposition)


def expire_due_leftovers(*, today=None, household=None) -> int:
    """Mark AVAILABLE leftovers whose stored expiration_date is in the past as EXPIRED,
    recording a scheduled FoodWasteEvent per leftover. Deterministic + idempotent
    (re-runs skip already-terminal rows). Returns the count expired. Never invents a
    date — only acts where expiration_date is stored."""
    today = today or timezone.now().date()
    base = Leftover.objects.filter(
        status="active", disposition=Leftover.DISP_AVAILABLE, servings__gt=0,
        expiration_date__isnull=False, expiration_date__lt=today,
    )
    if household is not None:
        base = base.filter(household=household)

    expired = 0
    for pk in list(base.values_list("pk", flat=True)):
        with transaction.atomic():
            lo = Leftover.objects.select_for_update().filter(pk=pk).first()
            if (lo is None or not lo.is_available or not lo.expiration_date
                    or lo.expiration_date >= today):
                continue  # state changed between the scan and the lock — skip
            FoodWasteEvent.objects.create(
                user=lo.user, household=lo.household, leftover=lo,
                preparation=lo.preparation, recipe=lo.recipe,
                recipe_title=lo.recipe_title, event_type=FoodWasteEvent.EVENT_EXPIRED,
                servings=lo.servings, reason="past stored expiration_date",
                source=FoodWasteEvent.SOURCE_SCHEDULED, occurred_at=timezone.now(),
            )
            lo.disposition = Leftover.DISP_EXPIRED
            lo.depleted_at = timezone.now()
            lo.save(update_fields=["disposition", "depleted_at", "updated_at"])
            expired += 1

    if expired:
        logger.info("expire_due_leftovers: marked %d leftover(s) expired", expired)
    return expired
