# ==============================================================================
# File: apps/core/ai_events/adapters/habits.py
# Project: Whole Life Journey
# Description: Habits event adapter
# Created: 2026-03-28
# ==============================================================================
"""Habits Event Adapter. Reads HabitEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.purpose.models import HabitEntry
    entries = HabitEntry.objects.filter(
        goal__user=user, date__gte=start_date, date__lte=end_date,
    ).select_related('goal').order_by('date')
    return [_to_event(e) for e in entries]


def get_latest(user, count=5):
    from apps.purpose.models import HabitEntry
    entries = HabitEntry.objects.filter(
        goal__user=user
    ).select_related('goal').order_by('-date')[:count]
    return [_to_event(e) for e in entries]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def get_missed_events(user, start_date, end_date):
    """Get habit entries that were not completed."""
    _enforce_bounds(start_date, end_date)
    from apps.purpose.models import HabitEntry
    entries = HabitEntry.objects.filter(
        goal__user=user, date__gte=start_date, date__lte=end_date,
        completed=False,
    ).select_related('goal').order_by('date')
    return [_to_event(e) for e in entries]


def _to_event(entry):
    from django.utils import timezone as tz
    goal_name = entry.goal.name if entry.goal else 'Habit'
    status = 'completed' if entry.completed else 'missed'
    label = f"{goal_name}"
    if entry.duration_minutes:
        label += f" ({entry.duration_minutes} min)"
    elif entry.count_value:
        label += f" ({entry.count_value})"

    timestamp = tz.make_aware(
        tz.datetime.combine(entry.date, tz.datetime.min.time()),
        tz.get_default_timezone(),
    )

    return EventRecord(
        domain='habits', event_type='habit_entry', timestamp=timestamp,
        label=label, status=status,
        detail={
            'habit_name': goal_name, 'completed': entry.completed,
            'duration_minutes': entry.duration_minutes,
            'count_value': entry.count_value,
            'date': str(entry.date),
        },
        source_model='HabitEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
