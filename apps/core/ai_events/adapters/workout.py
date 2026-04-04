# ==============================================================================
# File: apps/core/ai_events/adapters/workout.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Workout event adapter — reads WorkoutSession for event-level truth
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Workout Event Adapter.

Reads directly from WorkoutSession (source of truth) to provide event-level
detail for workout tracking.
"""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)

MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    """
    Get all workout events in date range.

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — workout events, sorted by date
    """
    _enforce_bounds(start_date, end_date)

    from apps.health.models import WorkoutSession

    sessions = (
        WorkoutSession.objects
        .filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
        )
        .order_by('date', 'started_at')
    )

    return [_session_to_event(s) for s in sessions]


def get_day_events(user, target_date):
    """Get all workout events for a specific date."""
    return get_events(user, target_date, target_date)


def _session_to_event(session):
    """Convert a WorkoutSession to an EventRecord."""
    from django.utils import timezone as tz

    # Determine completion status
    if session.completed_at:
        status = 'completed'
        event_type = 'workout_completed'
    elif session.started_at:
        status = 'in_progress'
        event_type = 'workout_started'
    else:
        status = 'logged'
        event_type = 'workout_logged'

    # Build label
    duration = f"{session.duration_minutes} min" if session.duration_minutes else ""
    if session.session_mode == 'activity' and session.workout_type:
        label = session.workout_type
        if duration:
            label += f" ({duration})"
    else:
        label = "Workout"
        if duration:
            label += f" ({duration})"

    # Use started_at or date for timestamp
    if session.started_at:
        timestamp = session.started_at
    else:
        naive_dt = tz.datetime.combine(session.date, tz.datetime.min.time())
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())

    detail = {
        'date': str(session.date),
        'duration_minutes': session.duration_minutes,
        'source': session.source or 'manual',
        'session_mode': session.session_mode,
        'intensity': session.intensity,
        'workout_type': session.workout_type,
    }
    if session.started_at:
        detail['started_at'] = session.started_at.isoformat()
    if session.completed_at:
        detail['completed_at'] = session.completed_at.isoformat()

    return EventRecord(
        domain='workout',
        event_type=event_type,
        timestamp=timestamp,
        label=label,
        status=status,
        detail=detail,
        source_model='WorkoutSession',
        source_id=session.pk,
    )


def _enforce_bounds(start_date, end_date):
    """Ensure queries are bounded and reasonable."""
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise ValueError("start_date and end_date must be date objects")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    span = (end_date - start_date).days
    if span > MAX_LOOKBACK_DAYS:
        raise ValueError(
            f"Date range exceeds maximum of {MAX_LOOKBACK_DAYS} days "
            f"(requested {span} days)"
        )
