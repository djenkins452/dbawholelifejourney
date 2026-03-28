# ==============================================================================
# File: apps/core/ai_events/adapters/glucose.py
# Project: Whole Life Journey
# Description: Glucose event adapter — reads GlucoseEntry
# Created: 2026-03-28
# ==============================================================================
"""Glucose Event Adapter. Reads GlucoseEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import GlucoseEntry
    entries = GlucoseEntry.objects.filter(
        user=user, recorded_at__date__gte=start_date,
        recorded_at__date__lte=end_date,
    ).order_by('recorded_at')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import GlucoseEntry
    return [_to_event(e) for e in GlucoseEntry.objects.filter(user=user).order_by('-recorded_at')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    context = entry.context or ''
    label = f"Glucose — {entry.value} {entry.unit}"
    if context:
        label += f" ({context})"
    return EventRecord(
        domain='glucose', event_type='glucose_logged', timestamp=entry.recorded_at,
        label=label, status='logged',
        detail={
            'value': float(entry.value), 'unit': entry.unit,
            'context': context, 'date': str(entry.recorded_at.date()),
            'trend': entry.trend or '',
        },
        source_model='GlucoseEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
