# ==============================================================================
# File: apps/core/ai_events/adapters/routine.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Routine event adapter — reads RoutineLog for event-level truth
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Routine Event Adapter.

Reads directly from RoutineLog (source of truth) to provide event-level
detail for routine tracking. Also computes "slippage" detection by
finding the inflection point where routine completion dropped.

Note: RoutineLog does NOT store "missed" entries — missed is the ABSENCE
of a log for a scheduled item on a given date. This adapter handles both
logged events (completed/skipped/rescheduled) and detected misses
(schedule was active, no log exists).
"""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)

MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    """
    Get all routine events in date range.

    Returns logged events only (completed, completed_late, skipped,
    rescheduled). Does NOT compute missing events — use
    get_missed_events() for that.

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — routine events, sorted by date/time
    """
    _enforce_bounds(start_date, end_date)

    from apps.life.models import RoutineLog

    logs = (
        RoutineLog.objects
        .filter(
            schedule__routine__user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        )
        .select_related('schedule', 'schedule__routine')
        .order_by('scheduled_date', 'schedule__scheduled_time')
    )

    return [_log_to_event(log) for log in logs]


def get_missed_events(user, start_date, end_date):
    """
    Get routine events that were NOT completed (skipped or no log at all).

    This includes:
    1. RoutineLogs with status 'skipped'
    2. RoutineSchedules that were active on a date but have no log

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — missed/skipped routine items, sorted by date
    """
    _enforce_bounds(start_date, end_date)

    from apps.life.models import RoutineLog, RoutineSchedule

    events = []

    # 1. Explicit skips (logged)
    skipped_logs = (
        RoutineLog.objects
        .filter(
            schedule__routine__user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
            log_status=RoutineLog.STATUS_SKIPPED,
        )
        .select_related('schedule', 'schedule__routine')
        .order_by('scheduled_date', 'schedule__scheduled_time')
    )
    for log in skipped_logs:
        events.append(_log_to_event(log))

    # 2. Missing logs (schedule active, no log exists)
    active_schedules = (
        RoutineSchedule.objects
        .filter(
            routine__user=user,
            routine__is_active=True,
            is_active=True,
        )
        .select_related('routine')
    )

    # Get all existing log (schedule_id, scheduled_date) pairs in range
    existing_logs = set(
        RoutineLog.objects
        .filter(
            schedule__routine__user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        )
        .values_list('schedule_id', 'scheduled_date')
    )

    # Check each date in range for missing logs
    current_date = start_date
    today = date.today()
    while current_date <= end_date and current_date < today:
        day_of_week = str(current_date.weekday())  # 0=Mon, 6=Sun
        for sched in active_schedules:
            # Check if this schedule applies to this day
            if sched.days_of_week and day_of_week not in sched.days_of_week.split(','):
                continue
            # Check for specific_date override
            if sched.specific_date and sched.specific_date != current_date:
                continue
            # Check if log exists
            if (sched.pk, current_date) not in existing_logs:
                events.append(_missing_to_event(sched, current_date))
        current_date += timedelta(days=1)

    # Sort by date then time
    events.sort(key=lambda e: e.timestamp)
    return events


def get_completion_trend(user, lookback_days=14):
    """
    Detect routine completion trend — find where slippage started.

    Returns a dict with:
        - daily_rates: list of (date, completion_rate) tuples
        - slippage_date: date when rate dropped below 80% (or None)
        - current_rate: latest 3-day average
        - prior_rate: 3-day average before slippage

    This is the deterministic answer to "when did my routine start slipping?"
    """
    from apps.life.models import RoutineLog, RoutineSchedule
    from django.db.models import Count, Q

    end = date.today() - timedelta(days=1)  # Yesterday (today incomplete)
    start = end - timedelta(days=lookback_days - 1)

    # Get active schedule count (expected items per applicable day)
    active_schedules = list(
        RoutineSchedule.objects
        .filter(
            routine__user=user,
            routine__is_active=True,
            is_active=True,
        )
        .values_list('pk', 'days_of_week')
    )

    if not active_schedules:
        return {
            'daily_rates': [],
            'slippage_date': None,
            'current_rate': None,
            'prior_rate': None,
        }

    # Get logs grouped by date
    logs_by_date = {}
    logs = (
        RoutineLog.objects
        .filter(
            schedule__routine__user=user,
            scheduled_date__gte=start,
            scheduled_date__lte=end,
            log_status__in=[
                RoutineLog.STATUS_COMPLETED,
                RoutineLog.STATUS_COMPLETED_LATE,
            ],
        )
        .values('scheduled_date')
        .annotate(completed_count=Count('pk'))
    )
    for entry in logs:
        logs_by_date[entry['scheduled_date']] = entry['completed_count']

    # Compute daily completion rates
    daily_rates = []
    current_date = start
    while current_date <= end:
        day_of_week = str(current_date.weekday())
        expected = sum(
            1 for _, days in active_schedules
            if not days or day_of_week in days.split(',')
        )
        if expected > 0:
            completed = logs_by_date.get(current_date, 0)
            rate = min(completed / expected, 1.0)
            daily_rates.append((current_date, rate))
        current_date += timedelta(days=1)

    if not daily_rates:
        return {
            'daily_rates': [],
            'slippage_date': None,
            'current_rate': None,
            'prior_rate': None,
        }

    # Find slippage point: first date where 3-day rolling avg drops below 80%
    slippage_date = None
    for i in range(2, len(daily_rates)):
        window = [daily_rates[j][1] for j in range(i - 2, i + 1)]
        avg = sum(window) / len(window)
        if avg < 0.8:
            slippage_date = daily_rates[i][0]
            break

    # Current rate (last 3 days)
    recent = [r for _, r in daily_rates[-3:]]
    current_rate = sum(recent) / len(recent) if recent else None

    # Prior rate (3 days before slippage, or first 3 days)
    if slippage_date and len(daily_rates) > 5:
        slip_idx = next(
            (i for i, (d, _) in enumerate(daily_rates) if d == slippage_date),
            None
        )
        if slip_idx and slip_idx >= 3:
            prior = [daily_rates[j][1] for j in range(slip_idx - 3, slip_idx)]
            prior_rate = sum(prior) / len(prior)
        else:
            prior = [r for _, r in daily_rates[:3]]
            prior_rate = sum(prior) / len(prior) if prior else None
    else:
        prior = [r for _, r in daily_rates[:3]]
        prior_rate = sum(prior) / len(prior) if prior else None

    return {
        'daily_rates': [(str(d), round(r * 100)) for d, r in daily_rates],
        'slippage_date': str(slippage_date) if slippage_date else None,
        'current_rate': round(current_rate * 100) if current_rate is not None else None,
        'prior_rate': round(prior_rate * 100) if prior_rate is not None else None,
    }


def get_day_events(user, target_date):
    """Get all routine events for a specific date."""
    return get_events(user, target_date, target_date)


def _log_to_event(log):
    """Convert a RoutineLog instance to an EventRecord."""
    from django.utils import timezone as tz

    sched = log.schedule
    routine_name = sched.routine.name if sched.routine_id else "Unknown"
    item_name = sched.name if sched else "Unknown"
    time_str = sched.scheduled_time.strftime("%-I:%M %p") if sched and sched.scheduled_time else ""

    label = f"{item_name}"
    if time_str:
        label += f" ({time_str})"
    label += f" — {routine_name}"

    # Map status
    status_map = {
        'completed': 'routine_completed',
        'completed_late': 'routine_completed_late',
        'skipped': 'routine_skipped',
        'rescheduled': 'routine_rescheduled',
    }
    event_type = status_map.get(log.log_status, f'routine_{log.log_status}')

    # Timestamp: use performed_at > completed_at > schedule time
    if log.performed_at:
        timestamp = log.performed_at
    elif log.completed_at:
        timestamp = log.completed_at
    elif sched and sched.scheduled_time:
        naive_dt = tz.datetime.combine(log.scheduled_date, sched.scheduled_time)
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())
    else:
        naive_dt = tz.datetime.combine(log.scheduled_date, tz.datetime.min.time())
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())

    detail = {
        'routine_name': routine_name,
        'item_name': item_name,
        'scheduled_date': str(log.scheduled_date),
        'log_status': log.log_status,
        'timing': log.timing or '',
        'completion_source': log.completion_source or '',
    }
    if log.source_object_id:
        detail['source_object_id'] = log.source_object_id

    return EventRecord(
        domain='routine',
        event_type=event_type,
        timestamp=timestamp,
        label=label,
        status=log.log_status,
        detail=detail,
        source_model='RoutineLog',
        source_id=log.pk,
    )


def _missing_to_event(schedule, target_date):
    """Create an EventRecord for a missing routine log (implicit miss)."""
    from django.utils import timezone as tz

    item_name = schedule.name
    routine_name = schedule.routine.name if schedule.routine_id else "Unknown"
    time_str = schedule.scheduled_time.strftime("%-I:%M %p") if schedule.scheduled_time else ""

    label = f"{item_name}"
    if time_str:
        label += f" ({time_str})"
    label += f" — {routine_name}"

    if schedule.scheduled_time:
        naive_dt = tz.datetime.combine(target_date, schedule.scheduled_time)
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())
    else:
        naive_dt = tz.datetime.combine(target_date, tz.datetime.min.time())
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())

    return EventRecord(
        domain='routine',
        event_type='routine_missed',
        timestamp=timestamp,
        label=label,
        status='missed',
        detail={
            'routine_name': routine_name,
            'item_name': item_name,
            'scheduled_date': str(target_date),
            'log_status': 'missed',
            'reason': 'no_log_found',
        },
        source_model='RoutineSchedule',
        source_id=schedule.pk,
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
