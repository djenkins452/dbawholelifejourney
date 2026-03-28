# ==============================================================================
# File: apps/core/ai_events/adapters/water.py
# Project: Whole Life Journey
# Description: Water intake event adapter
# Created: 2026-03-28
# ==============================================================================
"""Water Event Adapter. Reads WaterEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.health.models import WaterEntry
    entries = WaterEntry.objects.filter(
        user=user, logged_date__gte=start_date, logged_date__lte=end_date,
    ).order_by('logged_date', 'recorded_at')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.health.models import WaterEntry
    return [_to_event(e) for e in WaterEntry.objects.filter(user=user).order_by('-logged_date', '-recorded_at')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def get_daily_total(user, target_date):
    """Get total water intake for a date — returns (total, unit, entry_count)."""
    from apps.health.models import WaterEntry
    from django.db.models import Sum, Count
    result = WaterEntry.objects.filter(
        user=user, logged_date=target_date,
    ).aggregate(total=Sum('amount'), count=Count('id'))
    return result.get('total') or 0, 'oz', result.get('count') or 0


def _to_event(entry):
    from django.utils import timezone as tz
    label = f"Water — {entry.amount} {entry.unit}"
    timestamp = entry.recorded_at or tz.make_aware(
        tz.datetime.combine(entry.logged_date, tz.datetime.min.time()),
        tz.get_default_timezone(),
    )
    return EventRecord(
        domain='water', event_type='water_logged', timestamp=timestamp,
        label=label, status='logged',
        detail={
            'amount': float(entry.amount), 'unit': entry.unit,
            'date': str(entry.logged_date),
            'container': entry.container or '',
        },
        source_model='WaterEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
