# ==============================================================================
# File: apps/core/ai_events/adapters/faith.py
# Project: Whole Life Journey
# Description: Faith event adapter — prayers and Bible reading
# Created: 2026-03-28
# ==============================================================================
"""Faith Event Adapter. Reads PrayerRequest and UserReadingProgress."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    events = []
    events.extend(_get_prayer_events(user, start_date, end_date))
    events.extend(_get_reading_events(user, start_date, end_date))
    events.sort(key=lambda e: e.timestamp)
    return events


def get_latest(user, count=3):
    from apps.faith.models import PrayerRequest
    prayers = PrayerRequest.objects.filter(user=user).order_by('-created_at')[:count]
    return [_prayer_to_event(p) for p in prayers]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _get_prayer_events(user, start_date, end_date):
    from apps.faith.models import PrayerRequest
    prayers = PrayerRequest.objects.filter(
        user=user, created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).order_by('created_at')
    events = [_prayer_to_event(p) for p in prayers]
    # Also include prayers answered in range
    answered = PrayerRequest.objects.filter(
        user=user, is_answered=True,
        answered_at__date__gte=start_date, answered_at__date__lte=end_date,
    ).exclude(created_at__date__gte=start_date, created_at__date__lte=end_date)
    for p in answered:
        events.append(_prayer_to_event(p, answered_event=True))
    return events


def _get_reading_events(user, start_date, end_date):
    from apps.faith.models import UserReadingProgress
    readings = UserReadingProgress.objects.filter(
        user_plan__user=user, is_completed=True,
        completed_at__date__gte=start_date,
        completed_at__date__lte=end_date,
    ).select_related('user_plan', 'plan_day').order_by('completed_at')
    return [_reading_to_event(r) for r in readings]


def _prayer_to_event(prayer, answered_event=False):
    if answered_event:
        label = f"Prayer Answered — {prayer.title}"
        event_type = 'prayer_answered'
        status = 'answered'
        timestamp = prayer.answered_at
    else:
        label = f"Prayer — {prayer.title}"
        event_type = 'prayer_logged'
        status = 'answered' if prayer.is_answered else 'active'
        timestamp = prayer.created_at

    return EventRecord(
        domain='faith', event_type=event_type, timestamp=timestamp,
        label=label, status=status,
        detail={
            'title': prayer.title,
            'is_answered': prayer.is_answered,
            'priority': prayer.priority or '',
            'date': str(timestamp.date()) if timestamp else '',
        },
        source_model='PrayerRequest', source_id=prayer.pk,
    )


def _reading_to_event(progress):
    plan_name = ''
    if progress.user_plan:
        plan_name = getattr(progress.user_plan, 'name', '') or str(progress.user_plan)
    label = f"Bible Reading — {plan_name}" if plan_name else "Bible Reading"

    return EventRecord(
        domain='faith', event_type='bible_reading', timestamp=progress.completed_at,
        label=label, status='completed',
        detail={
            'plan': plan_name,
            'date': str(progress.completed_at.date()) if progress.completed_at else '',
        },
        source_model='UserReadingProgress', source_id=progress.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
