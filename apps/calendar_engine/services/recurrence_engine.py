# ==============================================================================
# File: calendar_engine/services/recurrence_engine.py
# Project: Whole Life Journey — Calendar Projection Layer
# Description: The calendar-native recurrence engine. DST-safe occurrence
#              expansion + per-occurrence exceptions. Shared by RecurrenceRule
#              (Calendar Events) and AvailabilityBlock. Task recurrence lives in
#              life.RecurrencePattern and is NOT merged here.
# Governing doc: docs/WLJ_CALENDAR_PROJECTION_ARCHITECTURE.md
# ==============================================================================
"""Calendar-native recurrence expansion.

One engine for all calendar-native recurring objects. Works in the recurrence's
local timezone so wall-clock time is preserved across DST boundaries (e.g. "6 PM
every Wednesday" stays 6 PM when the UTC offset shifts CST→CDT).

Per-occurrence exceptions ("edit/delete just this Friday") are honored here — the
single place recurrence + exceptions compose, so no consumer can forget them.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Iterable, List, Optional, Tuple

from django.utils import timezone as tz_utils

logger = logging.getLogger(__name__)

FREQ_DAILY = "daily"
FREQ_WEEKLY = "weekly"
FREQ_MONTHLY = "monthly"


def _advance_date(current_date: dt.date, frequency: str, interval: int, byweekday) -> dt.date:
    """Advance a date by the recurrence interval."""
    if frequency == FREQ_DAILY:
        return current_date + dt.timedelta(days=interval)
    if frequency == FREQ_WEEKLY:
        if byweekday:
            next_date = current_date + dt.timedelta(days=1)
            days_checked = 0
            while days_checked < 7 * max(interval, 1):
                if next_date.isoweekday() in byweekday:
                    return next_date
                next_date += dt.timedelta(days=1)
                days_checked += 1
            return current_date + dt.timedelta(weeks=interval)
        return current_date + dt.timedelta(weeks=interval)
    if frequency == FREQ_MONTHLY:
        month = current_date.month + interval
        year = current_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(current_date.day, 28)
        return current_date.replace(year=year, month=month, day=day)
    return current_date + dt.timedelta(days=1)


def _normalize_exceptions(exceptions: Optional[Iterable]) -> dict:
    """Map exceptions by their original occurrence instant (UTC) for O(1) lookup.

    Each exception must expose: original_start_dt, is_canceled, new_start_dt,
    new_end_dt.
    """
    out = {}
    if not exceptions:
        return out
    for exc in exceptions:
        try:
            key = exc.original_start_dt.astimezone(dt.timezone.utc)
        except Exception:
            continue
        out[key] = exc
    return out


def expand_occurrences(
    anchor_start,
    duration: dt.timedelta,
    *,
    frequency: str,
    byweekday=None,
    interval: int = 1,
    until_dt=None,
    count: Optional[int] = None,
    tz_name: str = "America/Chicago",
    range_start,
    range_end,
    exceptions: Optional[Iterable] = None,
    max_iterations: int = 1000,
) -> List[Tuple[object, object]]:
    """Expand a recurring series into (start, end) occurrence tuples within a range.

    - DST-safe: iterates in the series' local timezone, preserving wall-clock time.
    - Exception-aware: a canceled occurrence is dropped; a moved occurrence is
      emitted at its new time (if it lands in the range).
    """
    from zoneinfo import ZoneInfo

    interval = max(int(interval or 1), 1)
    byweekday = list(byweekday or [])
    exc_map = _normalize_exceptions(exceptions)

    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = tz_utils.get_current_timezone()

    local_start = anchor_start.astimezone(local_tz)
    local_time = local_start.time()
    current_date = local_start.date()

    occurrences: List[Tuple[object, object]] = []
    iteration = 0
    generated = 0

    while iteration < max_iterations:
        iteration += 1

        naive_dt = dt.datetime.combine(current_date, local_time)
        try:
            current = tz_utils.make_aware(naive_dt, local_tz)
        except Exception:
            current = naive_dt.replace(tzinfo=local_tz)

        if current > range_end:
            break
        if count is not None and generated >= count:
            break
        if until_dt is not None and current > until_dt:
            break

        # byweekday filter (advance if this day isn't in the set)
        if byweekday and current.isoweekday() not in byweekday:
            current_date = _advance_date(current_date, frequency, interval, byweekday)
            continue

        # count is consumed by every generated occurrence in the series, even
        # ones filtered out of the visible range — so it advances regardless.
        generated += 1

        # Per-occurrence exception handling.
        exc = exc_map.get(current.astimezone(dt.timezone.utc))
        if exc is not None:
            if getattr(exc, "is_canceled", False):
                current_date = _advance_date(current_date, frequency, interval, byweekday)
                continue
            new_start = getattr(exc, "new_start_dt", None)
            if new_start is not None:
                new_end = getattr(exc, "new_end_dt", None) or (new_start + duration)
                if range_start <= new_start <= range_end:
                    occurrences.append((new_start, new_end))
                current_date = _advance_date(current_date, frequency, interval, byweekday)
                continue

        if current >= range_start:
            occurrences.append((current, current + duration))

        current_date = _advance_date(current_date, frequency, interval, byweekday)

    return occurrences
