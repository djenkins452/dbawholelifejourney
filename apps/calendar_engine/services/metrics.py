"""
Domain Imbalance Bar — Metrics Service.

Computes scheduled minutes by domain for Today and This Week.
"""

import datetime as dt

from django.db.models import F, Sum
from django.db.models.functions import Coalesce, ExtractHour, ExtractMinute
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent


def compute_domain_minutes(user, range_start, range_end):
    """
    Compute total scheduled minutes per domain within a date range.

    Returns dict: {domain_name: minutes, ...}
    Also includes 'Uncategorized' for events with no domain.
    """
    events = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        start_dt__lt=range_end,
        end_dt__gt=range_start,
    ).select_related('domain')

    domain_minutes = {}

    for event in events:
        # Clip event to range boundaries
        effective_start = max(event.start_dt, range_start)
        effective_end = min(event.end_dt, range_end)
        minutes = max(0, int((effective_end - effective_start).total_seconds() / 60))

        if minutes <= 0:
            continue

        domain_name = event.domain.name if event.domain else 'Uncategorized'
        domain_minutes[domain_name] = domain_minutes.get(domain_name, 0) + minutes

    # Also account for recurring event occurrences
    recurring = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        recurrence__isnull=False,
    ).select_related('domain', 'recurrence')

    seen_event_ids = set(events.values_list('pk', flat=True))

    for event in recurring:
        if event.pk in seen_event_ids:
            continue  # Already counted as a direct event
        occurrences = event.recurrence.get_occurrences(range_start, range_end)
        for occ_start, occ_end in occurrences:
            effective_start = max(occ_start, range_start)
            effective_end = min(occ_end, range_end)
            minutes = max(0, int((effective_end - effective_start).total_seconds() / 60))
            if minutes > 0:
                domain_name = event.domain.name if event.domain else 'Uncategorized'
                domain_minutes[domain_name] = domain_minutes.get(domain_name, 0) + minutes

    return domain_minutes


def compute_domain_percentages(user, range_start, range_end):
    """
    Compute domain balance as percentages.

    Returns list of dicts: [{name, minutes, percentage, color}, ...]
    """
    domain_minutes = compute_domain_minutes(user, range_start, range_end)
    total = sum(domain_minutes.values())

    if total == 0:
        return []

    # Get domain colors
    from apps.purpose.models import LifeDomain
    domain_colors = dict(
        LifeDomain.objects.filter(is_active=True).values_list('name', 'color')
    )

    result = []
    for name, minutes in sorted(domain_minutes.items(), key=lambda x: -x[1]):
        result.append({
            'name': name,
            'minutes': minutes,
            'percentage': round((minutes / total) * 100, 1),
            'color': domain_colors.get(name, '#6b7280'),
        })

    return result


def get_today_balance(user):
    """Domain balance for today."""
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    start = timezone.make_aware(dt.datetime.combine(today, dt.time.min), tz)
    end = timezone.make_aware(dt.datetime.combine(today, dt.time.max), tz)
    return compute_domain_percentages(user, start, end)


def get_week_balance(user):
    """Domain balance for this week (Monday–Sunday)."""
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    monday = today - dt.timedelta(days=today.weekday())
    sunday = monday + dt.timedelta(days=6)
    start = timezone.make_aware(dt.datetime.combine(monday, dt.time.min), tz)
    end = timezone.make_aware(dt.datetime.combine(sunday, dt.time.max), tz)
    return compute_domain_percentages(user, start, end)
