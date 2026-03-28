# ==============================================================================
# File: apps/core/ai_events/adapters/steps.py
# Project: Whole Life Journey
# Description: Steps event adapter
# Created: 2026-03-28
# ==============================================================================
"""Steps Event Adapter. Reads StepsEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import StepsEntry
    entries = StepsEntry.objects.filter(
        user=user, logged_date__gte=start_date, logged_date__lte=end_date,
    ).order_by('logged_date')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import StepsEntry
    return [_to_event(e) for e in StepsEntry.objects.filter(user=user).order_by('-logged_date')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    from django.utils import timezone as tz
    label = f"Steps — {entry.count:,}"
    if entry.goal and entry.count >= entry.goal:
        label += " ✓ goal reached"
    timestamp = entry.recorded_at or tz.make_aware(
        tz.datetime.combine(entry.logged_date, tz.datetime.min.time()),
        tz.get_default_timezone(),
    )
    return EventRecord(
        domain='steps', event_type='steps_logged', timestamp=timestamp,
        label=label, status='logged',
        detail={
            'count': entry.count, 'goal': entry.goal,
            'date': str(entry.logged_date),
            'distance_miles': float(entry.distance_miles) if entry.distance_miles else None,
        },
        source_model='StepsEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
