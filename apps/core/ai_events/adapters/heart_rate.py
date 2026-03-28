# ==============================================================================
# File: apps/core/ai_events/adapters/heart_rate.py
# Project: Whole Life Journey
# Description: Heart rate event adapter
# Created: 2026-03-28
# ==============================================================================
"""Heart Rate Event Adapter. Reads HeartRateEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import HeartRateEntry
    entries = HeartRateEntry.objects.filter(
        user=user, recorded_at__date__gte=start_date,
        recorded_at__date__lte=end_date,
    ).order_by('recorded_at')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import HeartRateEntry
    return [_to_event(e) for e in HeartRateEntry.objects.filter(user=user).order_by('-recorded_at')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    context = entry.context or ''
    label = f"Heart Rate — {entry.bpm} bpm"
    if context:
        label += f" ({context})"
    return EventRecord(
        domain='heart_rate', event_type='hr_logged', timestamp=entry.recorded_at,
        label=label, status='logged',
        detail={
            'bpm': entry.bpm, 'context': context,
            'date': str(entry.recorded_at.date()),
        },
        source_model='HeartRateEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
