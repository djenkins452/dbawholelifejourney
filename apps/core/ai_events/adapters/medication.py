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

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end

    Returns:
        list[EventRecord] — missed doses only, sorted by date/time
    """
    _enforce_bounds(start_date, end_date)

    from apps.health.models import MedicineLog

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

    return [_log_to_event(log) for log in logs]


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
