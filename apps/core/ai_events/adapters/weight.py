# ==============================================================================
# File: apps/core/ai_events/adapters/weight.py
# Project: Whole Life Journey
# Description: Weight event adapter — reads WeightEntry for event-level truth
# Created: 2026-03-28
# ==============================================================================
"""Weight Event Adapter. Reads WeightEntry directly."""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import WeightEntry
    entries = (
        WeightEntry.objects.filter(
            user=user, recorded_at__date__gte=start_date,
            recorded_at__date__lte=end_date,
        ).order_by('recorded_at')
    )
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import WeightEntry
    entries = WeightEntry.objects.filter(user=user).order_by('-recorded_at')[:count]
    return [_to_event(e) for e in entries]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    label = f"Weight — {entry.value} {entry.unit}"
    return EventRecord(
        domain='weight', event_type='weight_logged', timestamp=entry.recorded_at,
        label=label, status='logged',
        detail={
            'value': float(entry.value), 'unit': entry.unit,
            'date': str(entry.recorded_at.date()),
        },
        source_model='WeightEntry', source_id=entry.pk,
    )


def _enforce_bounds(start_date, end_date):
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    if (end_date - start_date).days > MAX_LOOKBACK_DAYS:
        raise ValueError(f"Date range exceeds {MAX_LOOKBACK_DAYS} days")
