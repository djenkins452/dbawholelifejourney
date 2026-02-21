"""
Smart Gap Detection Service.

Finds open time windows and suggests execution blocks for items due soon.
"""

import datetime as dt

from django.db.models import Q
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent


# Configurable minimum gap in minutes
MIN_GAP_MINUTES = 90
LOOKAHEAD_DAYS = 14
EXECUTION_CHECK_DAYS = 7


def find_gaps_for_day(user, date=None):
    """
    Find open time windows in a user's day.
    Default work window: 6:00 AM - 10:00 PM.

    Returns list of dicts: {start_dt, end_dt, duration_minutes}
    """
    if date is None:
        date = timezone.localdate()

    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(dt.datetime.combine(date, dt.time(6, 0)), tz)
    day_end = timezone.make_aware(dt.datetime.combine(date, dt.time(22, 0)), tz)

    events = _get_events_for_range(user, day_start, day_end)

    # Sort by start time
    events.sort(key=lambda e: e[0])

    gaps = []
    cursor = day_start

    for evt_start, evt_end in events:
        if evt_start > cursor:
            gap_minutes = int((evt_start - cursor).total_seconds() / 60)
            if gap_minutes >= MIN_GAP_MINUTES:
                gaps.append({
                    'start_dt': cursor,
                    'end_dt': evt_start,
                    'duration_minutes': gap_minutes,
                })
        cursor = max(cursor, evt_end)

    # Gap after last event
    if cursor < day_end:
        gap_minutes = int((day_end - cursor).total_seconds() / 60)
        if gap_minutes >= MIN_GAP_MINUTES:
            gaps.append({
                'start_dt': cursor,
                'end_dt': day_end,
                'duration_minutes': gap_minutes,
            })

    return gaps


def _get_events_for_range(user, range_start, range_end):
    """
    Get all event time ranges (including recurring occurrences) for a user
    within the given range. Returns list of (start_dt, end_dt) tuples.
    """
    # Non-recurring events
    events = list(
        CalendarEvent.objects.filter(
            user=user,
            status=CalendarEvent.STATUS_SCHEDULED,
            start_dt__lt=range_end,
            end_dt__gt=range_start,
        ).values_list('start_dt', 'end_dt')
    )

    # Recurring events — check all recurring events that could have occurrences in range
    recurring = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        recurrence__isnull=False,
    ).select_related('recurrence')

    for event in recurring:
        occurrences = event.recurrence.get_occurrences(range_start, range_end)
        events.extend(occurrences)

    return events


def get_items_due_soon(user):
    """
    Find tasks and goals due within LOOKAHEAD_DAYS that have
    zero execution blocks scheduled in the next EXECUTION_CHECK_DAYS.
    """
    from apps.life.models import Task
    from apps.purpose.models import LifeGoal

    now = timezone.now()
    lookahead = now + dt.timedelta(days=LOOKAHEAD_DAYS)
    exec_window = now + dt.timedelta(days=EXECUTION_CHECK_DAYS)

    items = []

    # Tasks due soon without execution blocks
    tasks = Task.objects.filter(
        user=user,
        is_completed=False,
        due_date__isnull=False,
        due_date__lte=lookahead.date(),
        due_date__gte=now.date(),
    ).order_by('due_date')

    for task in tasks:
        has_blocks = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_TASK,
            source_id=str(task.pk),
            event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
            status=CalendarEvent.STATUS_SCHEDULED,
            start_dt__lte=exec_window,
        ).exists()

        if not has_blocks:
            items.append({
                'source_type': 'task',
                'source_id': str(task.pk),
                'title': task.title,
                'due_date': task.due_date.strftime('%m/%d/%Y'),
                'priority': task.priority,
                'effort': task.effort,
            })

    # Goals due soon without execution blocks
    goals = LifeGoal.objects.filter(
        user=user,
        status='active',
        target_date__isnull=False,
        target_date__lte=lookahead.date(),
        target_date__gte=now.date(),
    ).order_by('target_date')

    for goal in goals:
        has_blocks = CalendarEvent.objects.filter(
            user=user,
            source_type=CalendarEvent.SOURCE_GOAL,
            source_id=str(goal.pk),
            event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
            status=CalendarEvent.STATUS_SCHEDULED,
            start_dt__lte=exec_window,
        ).exists()

        if not has_blocks:
            items.append({
                'source_type': 'goal',
                'source_id': str(goal.pk),
                'title': goal.title,
                'due_date': goal.target_date.strftime('%m/%d/%Y'),
            })

    return items


def generate_suggestions(user, date=None):
    """
    Main entry point: find gaps, find items due soon, generate suggestions.
    Returns list of suggestion dicts.
    """
    gaps = find_gaps_for_day(user, date)
    items = get_items_due_soon(user)

    if not gaps or not items:
        return []

    suggestions = []
    gap_idx = 0

    for item in items:
        if gap_idx >= len(gaps):
            break

        gap = gaps[gap_idx]
        # Use first 90 minutes of the gap (or full gap if ≤ 90)
        block_duration = min(MIN_GAP_MINUTES, gap['duration_minutes'])
        block_end = gap['start_dt'] + dt.timedelta(minutes=block_duration)

        suggestions.append({
            'title': f"Work on: {item['title']}",
            'start_dt': gap['start_dt'].isoformat(),
            'end_dt': block_end.isoformat(),
            'source_type': item['source_type'],
            'source_id': item['source_id'],
            'rationale': f"'{item['title']}' is due {item['due_date']} with no execution time scheduled.",
        })

        # Advance gap cursor — if gap has room left, keep it; else move to next
        remaining = gap['duration_minutes'] - block_duration
        if remaining >= MIN_GAP_MINUTES:
            gaps[gap_idx] = {
                'start_dt': block_end,
                'end_dt': gap['end_dt'],
                'duration_minutes': remaining,
            }
        else:
            gap_idx += 1

    return suggestions
