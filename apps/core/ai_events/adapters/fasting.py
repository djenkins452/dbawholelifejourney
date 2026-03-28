# ==============================================================================
# File: apps/core/ai_events/adapters/fasting.py
# Project: Whole Life Journey
# Description: Fasting event adapter
# Created: 2026-03-28
# ==============================================================================
"""Fasting Event Adapter. Reads FastingWindow directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import FastingWindow
    entries = FastingWindow.objects.filter(
        user=user, started_at__date__gte=start_date,
        started_at__date__lte=end_date,
    ).order_by('started_at')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import FastingWindow
    return [_to_event(e) for e in FastingWindow.objects.filter(user=user).order_by('-started_at')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    duration = None
    if entry.ended_at and entry.started_at:
        duration = round((entry.ended_at - entry.started_at).total_seconds() / 3600, 1)
    status = 'in_progress' if not entry.ended_at else 'completed'
    label = f"Fast — {entry.fasting_type}"
    if duration:
        label += f" ({duration}h)"
    elif not entry.ended_at:
        label += " (active)"

    return EventRecord(
        domain='fasting', event_type='fast_logged', timestamp=entry.started_at,
        label=label, status=status,
        detail={
            'fasting_type': entry.fasting_type, 'target_hours': entry.target_hours,
            'duration_hours': duration,
            'started_at': entry.started_at.isoformat(),
            'ended_at': entry.ended_at.isoformat() if entry.ended_at else None,
            'date': str(entry.started_at.date()),
        },
        source_model='FastingWindow', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
