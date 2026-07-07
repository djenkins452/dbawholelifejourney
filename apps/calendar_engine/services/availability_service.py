# ==============================================================================
# File: calendar_engine/services/availability_service.py
# Project: Whole Life Journey — Calendar Projection Layer
# Description: Mutation service for Availability Blocks, including Outlook-style
#              recurring edits: this occurrence / this and future / entire series.
# Governing doc: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
# ==============================================================================
"""AvailabilityService — create/update/delete Availability Blocks.

Recurring edits follow Outlook semantics for calendar-native objects:
  - SERIES     : edit the base block + its recurrence in place.
  - FUTURE     : split — cap the original series at the boundary and create a new
                 block from the boundary forward with the changes.
  - OCCURRENCE : a single-occurrence move/cancel via AvailabilityException.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.db import transaction

from apps.calendar_engine.models import AvailabilityBlock, AvailabilityException

logger = logging.getLogger(__name__)

SCOPE_SERIES = "series"
SCOPE_FUTURE = "future"
SCOPE_OCCURRENCE = "occurrence"

_EDITABLE_FIELDS = (
    "label", "kind", "start_dt", "end_dt",
    "frequency", "byweekday", "interval", "until_dt", "count", "timezone",
)


def create_block(user, **fields) -> AvailabilityBlock:
    """Create an AvailabilityBlock. Only known fields are accepted."""
    clean = {k: v for k, v in fields.items() if k in _EDITABLE_FIELDS}
    return AvailabilityBlock.objects.create(user=user, **clean)


@transaction.atomic
def update_series(block: AvailabilityBlock, **fields) -> AvailabilityBlock:
    """Edit the entire series (the base block + recurrence)."""
    changed = []
    for k, v in fields.items():
        if k in _EDITABLE_FIELDS:
            setattr(block, k, v)
            changed.append(k)
    if changed:
        block.save(update_fields=changed + ["updated_at"])
    return block


@transaction.atomic
def edit_occurrence(block: AvailabilityBlock, original_start_dt,
                    new_start_dt=None, new_end_dt=None) -> AvailabilityException:
    """Move a single occurrence (this occurrence only)."""
    exc, _ = AvailabilityException.objects.update_or_create(
        block=block, original_start_dt=original_start_dt,
        defaults={
            "new_start_dt": new_start_dt,
            "new_end_dt": new_end_dt,
            "is_canceled": False,
        },
    )
    return exc


@transaction.atomic
def cancel_occurrence(block: AvailabilityBlock, original_start_dt) -> AvailabilityException:
    """Delete a single occurrence (this occurrence only)."""
    exc, _ = AvailabilityException.objects.update_or_create(
        block=block, original_start_dt=original_start_dt,
        defaults={"is_canceled": True, "new_start_dt": None, "new_end_dt": None},
    )
    return exc


@transaction.atomic
def split_future(block: AvailabilityBlock, boundary_start, **fields) -> AvailabilityBlock:
    """Split the series at *boundary_start*: cap the original series just before
    the boundary and create a new block from the boundary forward with *fields*.

    Returns the NEW (future) block.
    """
    # Cap the original series so it ends before the boundary occurrence.
    block.until_dt = boundary_start - dt.timedelta(seconds=1)
    block.save(update_fields=["until_dt", "updated_at"])

    # Seed the new block from the original, then apply the edits.
    seed = {f: getattr(block, f) for f in _EDITABLE_FIELDS}
    seed["start_dt"] = boundary_start
    # New block starts fresh — its own end anchor and no inherited cap unless set.
    seed["until_dt"] = None
    for k, v in fields.items():
        if k in _EDITABLE_FIELDS:
            seed[k] = v
    # Preserve occurrence duration if only the start moved.
    if "end_dt" not in fields:
        duration = block.end_dt - block.start_dt
        seed["end_dt"] = seed["start_dt"] + duration

    return AvailabilityBlock.objects.create(user=block.user, **seed)


@transaction.atomic
def delete_block(block: AvailabilityBlock, scope: str = SCOPE_SERIES,
                 occurrence_start=None) -> None:
    """Delete per scope: whole series (soft-delete), or a single occurrence."""
    if scope == SCOPE_OCCURRENCE and occurrence_start is not None:
        cancel_occurrence(block, occurrence_start)
        return
    if scope == SCOPE_FUTURE and occurrence_start is not None:
        # Truncate the series at the boundary; keep past occurrences.
        block.until_dt = occurrence_start - dt.timedelta(seconds=1)
        block.save(update_fields=["until_dt", "updated_at"])
        return
    block.soft_delete()
