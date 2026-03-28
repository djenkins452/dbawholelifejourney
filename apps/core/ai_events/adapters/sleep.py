# ==============================================================================
# File: apps/core/ai_events/adapters/sleep.py
# Project: Whole Life Journey
# Description: Sleep event adapter — reads SleepEntry for event-level truth
# Created: 2026-03-28
# ==============================================================================
"""Sleep Event Adapter. Reads SleepEntry directly."""

import logging
from datetime import date, timedelta

from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import SleepEntry
    entries = (
        SleepEntry.objects.filter(
            user=user, sleep_date__gte=start_date, sleep_date__lte=end_date,
        ).order_by('sleep_date')
    )
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import SleepEntry
    entries = SleepEntry.objects.filter(user=user).order_by('-sleep_date')[:count]
    return [_to_event(e) for e in entries]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    from django.utils import timezone as tz
    hours = round(entry.total_duration_minutes / 60, 1) if entry.total_duration_minutes else None
    quality = entry.quality_rating or ''
    label = f"Sleep — {hours}h" if hours else "Sleep"
    if quality:
        label += f" ({quality})"

    timestamp = entry.bedtime or tz.make_aware(
        tz.datetime.combine(entry.sleep_date, tz.datetime.min.time()),
        tz.get_default_timezone(),
    )

    detail = {
        'sleep_date': str(entry.sleep_date),
        'hours': hours,
        'total_duration_minutes': entry.total_duration_minutes,
        'quality_rating': quality,
        'quality_score': entry.quality_score,
    }
    if entry.bedtime:
        detail['bedtime'] = entry.bedtime.isoformat()
    if entry.wake_time:
        detail['wake_time'] = entry.wake_time.isoformat()
    if entry.stage_deep_minutes:
        detail['deep_minutes'] = entry.stage_deep_minutes
    if entry.stage_rem_minutes:
        detail['rem_minutes'] = entry.stage_rem_minutes

    return EventRecord(
        domain='sleep', event_type='sleep_logged', timestamp=timestamp,
        label=label, status='logged', detail=detail,
        source_model='SleepEntry', source_id=entry.pk,
    )


def _enforce_bounds(start_date, end_date):
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    if (end_date - start_date).days > MAX_LOOKBACK_DAYS:
        raise ValueError(f"Date range exceeds {MAX_LOOKBACK_DAYS} days")
