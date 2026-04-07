# ==============================================================================
# File: apps/core/ai_events/adapters/workout.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Workout event adapter — reads WorkoutSession for event-level truth
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Workout Event Adapter.

Date-aware adapter following the WLJ pattern of "Raw Data → Signals/State →
CoS → LLM". For past/today dates we read from WorkoutSession (logged truth).
For future dates we read from WorkoutSchedule (planned truth) so the
deterministic event pipeline can answer "what is my workout tomorrow?"
without ever falling through to LLM hallucination.

Mixed ranges (e.g. last 3 days through next 3 days) return the union,
sorted by date. Past/today behavior is preserved verbatim.
"""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)

MAX_LOOKBACK_DAYS = 30
MAX_FORWARD_DAYS = 14   # Symmetric forward cap for scheduled lookups


def get_events(user, start_date, end_date):
    """
    Get all workout events in date range.

    Past/today dates → WorkoutSession (logged truth, source of execution).
    Future dates     → WorkoutSchedule (planned truth, source of intent).
    Mixed ranges return the union, sorted by date.

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — workout events, sorted by date
    """
    _enforce_bounds(start_date, end_date)

    today = date.today()
    events = []

    # Past / today branch — UNCHANGED query
    past_end = min(end_date, today)
    if start_date <= past_end:
        from apps.health.models import WorkoutSession

        sessions = (
            WorkoutSession.objects
            .filter(
                user=user,
                date__gte=start_date,
                date__lte=past_end,
            )
            .order_by('date', 'started_at')
        )
        events.extend(_session_to_event(s) for s in sessions)

    # Future branch — NEW: deterministic schedule lookup
    future_start = max(start_date, today + timedelta(days=1))
    if future_start <= end_date:
        events.extend(_scheduled_events(user, future_start, end_date))

    return events


def _scheduled_events(user, start_date, end_date):
    """
    Return one EventRecord per scheduled (non-rest) day in [start_date, end_date].

    Reads the active WorkoutPlan's WorkoutSchedule rows once and projects them
    onto the requested calendar window. Deterministic — no LLM, no inference.
    """
    if (end_date - start_date).days > MAX_FORWARD_DAYS:
        raise ValueError(
            f"Forward range exceeds maximum of {MAX_FORWARD_DAYS} days"
        )

    from apps.health.models import WorkoutSchedule

    schedule_by_dow = {
        s.day_of_week: s
        for s in (
            WorkoutSchedule.objects
            .filter(plan__user=user, plan__is_active=True)
            .select_related('template', 'plan')
        )
    }
    if not schedule_by_dow:
        return []

    out = []
    cur = start_date
    while cur <= end_date:
        entry = schedule_by_dow.get(cur.weekday())
        if entry and not entry.is_rest_day:
            out.append(_schedule_to_event(entry, cur))
        cur += timedelta(days=1)
    return out


def _schedule_to_event(entry, target_date):
    """Convert a WorkoutSchedule row + concrete date into an EventRecord."""
    from django.utils import timezone as tz

    base_time = entry.preferred_time or tz.datetime.min.time()
    naive_dt = tz.datetime.combine(target_date, base_time)
    timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())

    return EventRecord(
        domain='workout',
        event_type='workout_scheduled',
        timestamp=timestamp,
        label=entry.template.name,
        status='scheduled',
        detail={
            'date': str(target_date),
            'day_of_week': target_date.strftime('%A'),
            'plan_name': entry.plan.name,
            'template_name': entry.template.name,
            'preferred_time': (
                entry.preferred_time.isoformat()
                if entry.preferred_time else None
            ),
            'is_rest_day': False,
        },
        source_model='WorkoutSchedule',
        source_id=entry.pk,
    )


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
    """
    Ensure queries are bounded and reasonable.

    Past span is bounded by MAX_LOOKBACK_DAYS; the forward span is bounded
    by MAX_FORWARD_DAYS inside _scheduled_events. The total span check uses
    the past cap (the broader of the two) so existing past-only callers
    behave identically.
    """
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise ValueError("start_date and end_date must be date objects")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    today = date.today()
    past_span = (min(end_date, today) - start_date).days if start_date <= today else 0
    if past_span > MAX_LOOKBACK_DAYS:
        raise ValueError(
            f"Date range exceeds maximum of {MAX_LOOKBACK_DAYS} days "
            f"(requested {past_span} days)"
        )
