# ==============================================================================
# File: apps/core/ai_events/adapters/blood_pressure.py
# Project: Whole Life Journey
# Description: Blood pressure event adapter
# Created: 2026-03-28
# ==============================================================================
"""Blood Pressure Event Adapter. Reads BloodPressureEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import BloodPressureEntry
    entries = BloodPressureEntry.objects.filter(
        user=user, recorded_at__date__gte=start_date,
        recorded_at__date__lte=end_date,
    ).order_by('recorded_at')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import BloodPressureEntry
    return [_to_event(e) for e in BloodPressureEntry.objects.filter(user=user).order_by('-recorded_at')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    context = entry.context or ''
    label = f"Blood Pressure — {entry.systolic}/{entry.diastolic} mmHg"
    if entry.pulse:
        label += f" (pulse {entry.pulse})"
    return EventRecord(
        domain='blood_pressure', event_type='bp_logged', timestamp=entry.recorded_at,
        label=label, status='logged',
        detail={
            'systolic': entry.systolic, 'diastolic': entry.diastolic,
            'pulse': entry.pulse, 'context': context,
            'date': str(entry.recorded_at.date()),
        },
        source_model='BloodPressureEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
