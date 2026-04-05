# ==============================================================================
# File: apps/core/ai_events/adapters/medication.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Medication event adapter — reads MedicineLog for event-level truth
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Medication Event Adapter.

Reads directly from MedicineLog (source of truth) to provide event-level
detail for medication tracking. Does NOT read from ComplianceEvent or SAE.

Queries are always bounded by date range and user-scoped.
"""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)

# Maximum lookback to prevent unbounded queries
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    """
    Get all medication events in date range.

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — all medication events, sorted by date/time
    """
    _enforce_bounds(start_date, end_date)

    from apps.health.models import MedicineLog

    logs = (
        MedicineLog.objects
        .filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        )
        .select_related('medicine', 'schedule')
        .order_by('scheduled_date', 'scheduled_time')
    )

    return [_log_to_event(log) for log in logs]


def get_missed_events(user, start_date, end_date):
    """
    Get only missed medication events in date range.

    This is the primary query for "what did I miss?" questions.

    Includes BOTH:
    - Doses explicitly logged as missed (log_status='missed')
    - Expected doses with NO log entry at all (unlogged = missed)

    This matches the dashboard/CoS adherence calculation in medicine_utils.py
    which correctly treats unlogged expected doses as not taken.

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — missed doses only, sorted by date/time
    """
    _enforce_bounds(start_date, end_date)

    from apps.health.models import MedicineLog

    # 1. Explicitly logged misses
    logs = (
        MedicineLog.objects
        .filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
            log_status=MedicineLog.STATUS_MISSED,
        )
        .select_related('medicine', 'schedule')
        .order_by('scheduled_date', 'scheduled_time')
    )
    events = [_log_to_event(log) for log in logs]

    # 2. Unlogged expected doses (scheduled but no log entry exists)
    unlogged = _find_unlogged_doses(user, start_date, end_date)
    events.extend(unlogged)

    # Sort combined results by timestamp
    events.sort(key=lambda e: e.timestamp)
    return events


def get_skipped_events(user, start_date, end_date):
    """Get only skipped medication events in date range."""
    _enforce_bounds(start_date, end_date)

    from apps.health.models import MedicineLog

    logs = (
        MedicineLog.objects
        .filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
            log_status=MedicineLog.STATUS_SKIPPED,
        )
        .select_related('medicine', 'schedule')
        .order_by('scheduled_date', 'scheduled_time')
    )

    return [_log_to_event(log) for log in logs]


def get_late_events(user, start_date, end_date):
    """Get doses taken late in date range."""
    _enforce_bounds(start_date, end_date)

    from apps.health.models import MedicineLog

    logs = (
        MedicineLog.objects
        .filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
            log_status=MedicineLog.STATUS_LATE,
        )
        .select_related('medicine', 'schedule')
        .order_by('scheduled_date', 'scheduled_time')
    )

    return [_log_to_event(log) for log in logs]


def get_day_events(user, target_date):
    """Get all medication events for a specific date."""
    return get_events(user, target_date, target_date)


def _find_unlogged_doses(user, start_date, end_date):
    """
    Find expected doses that have NO log entry at all.

    Walks active medicine schedules day-by-day (same approach as
    medicine_utils.calculate_medicine_adherence) and checks for missing
    MedicineLog rows. For today, skips future doses (not due yet).

    Returns list[EventRecord] for each unlogged dose.
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import Medicine, MedicineLog

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()

    active_medicines = Medicine.objects.filter(
        user=user,
        medicine_status=Medicine.STATUS_ACTIVE,
    ).prefetch_related("schedules")

    # Build set of (medicine_id, scheduled_date) pairs that have log entries
    existing_logs = set(
        MedicineLog.objects.filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        ).values_list('medicine_id', 'schedule_id', 'scheduled_date')
    )

    events = []
    day = start_date
    while day <= end_date:
        day_of_week = day.weekday()
        is_today = (day == user_today)
        # Don't report future days as missed
        if day > user_today:
            break
        for medicine in active_medicines:
            for schedule in medicine.schedules.filter(is_active=True):
                if not schedule.applies_to_day(day_of_week):
                    continue
                # Skip future doses today — can't miss what isn't due yet
                if is_today and schedule.scheduled_time and schedule.scheduled_time > current_time:
                    continue
                # Check if a log entry exists for this schedule+date
                if (medicine.id, schedule.id, day) not in existing_logs:
                    events.append(
                        _unlogged_to_event(medicine, schedule, day, user)
                    )
        day += timedelta(days=1)

    return events


def _unlogged_to_event(medicine, schedule, scheduled_date, user):
    """Convert an unlogged expected dose into an EventRecord."""
    from django.utils import timezone as tz

    time_str = schedule.scheduled_time.strftime("%-I:%M %p") if schedule.scheduled_time else "unscheduled"
    dose_str = medicine.dose if medicine.dose else ""
    label = f"{medicine.name}"
    if dose_str:
        label += f" ({dose_str})"
    label += f" — {time_str}"

    # Build timestamp
    if schedule.scheduled_time:
        naive_dt = tz.datetime.combine(scheduled_date, schedule.scheduled_time)
    else:
        naive_dt = tz.datetime.combine(scheduled_date, tz.datetime.min.time())
    try:
        user_tz = _get_user_timezone(user)
        timestamp = tz.make_aware(naive_dt, user_tz)
    except Exception:
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())

    detail = {
        'medicine_name': medicine.name,
        'dose': dose_str,
        'scheduled_date': str(scheduled_date),
        'scheduled_time': str(schedule.scheduled_time) if schedule.scheduled_time else None,
        'log_status': 'unlogged',
        'intake_type': medicine.intake_type,
        'priority': medicine.priority,
    }

    return EventRecord(
        domain='medication',
        event_type='dose_missed',
        timestamp=timestamp,
        label=label,
        status='missed',
        detail=detail,
        source_model='MedicineSchedule',
        source_id=schedule.pk,
    )


def _log_to_event(log):
    """Convert a MedicineLog instance to an EventRecord."""
    from django.utils import timezone as tz

    # Build human-readable label
    time_str = log.scheduled_time.strftime("%-I:%M %p") if log.scheduled_time else "unscheduled"
    med_name = log.medicine.name if log.medicine_id else "Unknown"
    dose_str = log.medicine.dose if log.medicine_id and log.medicine.dose else ""
    label = f"{med_name}"
    if dose_str:
        label += f" ({dose_str})"
    label += f" — {time_str}"

    # Map log_status to event_type
    status_map = {
        'taken': 'dose_taken',
        'missed': 'dose_missed',
        'skipped': 'dose_skipped',
        'late': 'dose_taken_late',
    }
    event_type = status_map.get(log.log_status, f'dose_{log.log_status}')

    # Build timestamp from scheduled_date + scheduled_time
    if log.scheduled_time:
        naive_dt = tz.datetime.combine(log.scheduled_date, log.scheduled_time)
        try:
            user_tz = _get_user_timezone(log.user)
            timestamp = tz.make_aware(naive_dt, user_tz)
        except Exception:
            timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())
    else:
        # No scheduled time — use noon as fallback
        naive_dt = tz.datetime.combine(log.scheduled_date, tz.datetime.min.time())
        timestamp = tz.make_aware(naive_dt, tz.get_default_timezone())

    # Detail dict with extra context
    detail = {
        'medicine_name': med_name,
        'dose': dose_str,
        'scheduled_date': str(log.scheduled_date),
        'scheduled_time': str(log.scheduled_time) if log.scheduled_time else None,
        'log_status': log.log_status,
        'intake_type': log.medicine.intake_type if log.medicine_id else 'medication',
        'priority': log.medicine.priority if log.medicine_id else 'critical',
    }
    if log.taken_at:
        detail['taken_at'] = log.taken_at.isoformat()
    if log.is_prn_dose:
        detail['is_prn'] = True
        if log.prn_reason:
            detail['prn_reason'] = log.prn_reason

    return EventRecord(
        domain='medication',
        event_type=event_type,
        timestamp=timestamp,
        label=label,
        status=log.log_status,
        detail=detail,
        source_model='MedicineLog',
        source_id=log.pk,
    )


def _get_user_timezone(user):
    """Get user's timezone from preferences."""
    from django.utils import timezone as tz
    try:
        import zoneinfo
        tz_name = user.preferences.timezone_iana or user.preferences.timezone or 'America/Chicago'
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return tz.get_default_timezone()


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
