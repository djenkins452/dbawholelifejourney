"""
Time Intelligence Engine.

Computes whether the user is ON_TRACK, USING_BUFFER, or LATE
based on their full daily schedule — considering task durations,
sequencing, and inter-task buffers.

The key insight: "late" is not about the clock vs one item.
It's about whether the remaining schedule is still achievable.

Example:
    5:19 AM, schedule: Prayer 5:30 (15m), Bible 5:45 (15m), Workout 6:15 (45m)
    → Even if 11 minutes to Prayer, the full chain completes by 7:00
    → Total slack = (5:45 - 5:45) + (6:15 - 6:00) = 15 min buffer
    → Status: ON_TRACK (buffer absorbs any small delay)

States:
    ON_TRACK:     Current time + remaining durations fits within schedule
    USING_BUFFER: Some scheduled starts have passed, but completion
                  is still reachable using available slack
    LATE:         Mathematically impossible to complete remaining items
                  on time (cumulative delay exceeds total slack)
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default duration for routine items without explicit duration (minutes)
DEFAULT_ITEM_DURATION = 15

# Buffer threshold: if total slack < this, user is USING_BUFFER
BUFFER_WARNING_MINUTES = 5


def compute_time_status(user) -> dict:
    """
    Compute the user's time status against their daily schedule.

    Returns:
        {
            'status': 'ON_TRACK' | 'USING_BUFFER' | 'LATE',
            'next_item': str or None,
            'next_item_time': str or None,
            'minutes_until_next': int or None,
            'total_slack_minutes': int,
            'message': str,
        }
    """
    try:
        from apps.core.utils import get_user_now, get_user_today
        from apps.core.execution.execution_truth_engine import get_execution_truth

        now = get_user_now(user)
        today = get_user_today(user)
        current_time = now.time()

        # Get today's scheduled items from routine system
        items = _get_scheduled_items(user, today)
        if not items:
            return {
                'status': 'ON_TRACK',
                'next_item': None,
                'next_item_time': None,
                'minutes_until_next': None,
                'total_slack_minutes': 0,
                'message': 'No scheduled items today.',
            }

        # Get execution truth to know what's already done
        truth = get_execution_truth(user, today)

        # Filter to remaining (not-yet-completed) items
        remaining = _filter_remaining(items, truth, today)
        if not remaining:
            return {
                'status': 'ON_TRACK',
                'next_item': None,
                'next_item_time': None,
                'minutes_until_next': None,
                'total_slack_minutes': 0,
                'message': 'All scheduled items completed.',
            }

        # Compute schedule math
        status, slack, message = _compute_schedule_status(
            remaining, current_time,
        )

        next_item = remaining[0]
        next_time = next_item['scheduled_time']
        minutes_until = _minutes_between(current_time, next_time)

        return {
            'status': status,
            'next_item': next_item['name'],
            'next_item_time': next_time.strftime('%I:%M %p').lstrip('0'),
            'minutes_until_next': max(0, minutes_until),
            'total_slack_minutes': max(0, slack),
            'message': message,
        }

    except Exception as e:
        logger.warning("Time intelligence computation failed: %s", e)
        return {
            'status': 'ON_TRACK',
            'next_item': None,
            'next_item_time': None,
            'minutes_until_next': None,
            'total_slack_minutes': 0,
            'message': '',
        }


def _get_scheduled_items(user, today) -> List[dict]:
    """
    Get today's scheduled routine items, sorted by time.

    Returns list of dicts: {name, scheduled_time, duration_minutes, domain}
    """
    try:
        from apps.life.models import RoutineSchedule

        # Get active routine schedules for today's day of week
        dow = str(today.weekday())  # 0=Monday
        schedules = RoutineSchedule.objects.filter(
            routine__user=user,
            routine__is_active=True,
            is_active=True,
        ).filter(
            days_of_week__contains=dow,
        ).select_related('routine').order_by('scheduled_time')

        # Phase 7 Fix: RoutineSchedule has no `duration_minutes` field
        # (it has grace_period_minutes, which is a different semantic
        # — how long after scheduled_time you have before the task is
        # considered late). Fall back to DEFAULT_ITEM_DURATION for all
        # routine items. (Audit 2026-04-08.)
        items = []
        for s in schedules:
            if s.scheduled_time:
                items.append({
                    'name': s.name,
                    'scheduled_time': s.scheduled_time,
                    'duration_minutes': DEFAULT_ITEM_DURATION,
                    'domain': s.activity_type or 'routine',
                    'schedule_id': s.id,
                })

        return items
    except Exception:
        logger.warning("Failed to get scheduled items", exc_info=True)
        return []


def _filter_remaining(
    items: List[dict], truth: dict, today,
) -> List[dict]:
    """Filter out items that are already completed."""
    from apps.life.models import RoutineLog

    completed_schedule_ids = set(
        RoutineLog.objects.filter(
            schedule__routine__user_id=truth.get('_user_id'),
            scheduled_date=today,
            log_status__in=['completed', 'completed_late'],
        ).values_list('schedule_id', flat=True)
    ) if truth else set()

    return [
        item for item in items
        if item['schedule_id'] not in completed_schedule_ids
    ]


def _compute_schedule_status(
    remaining: List[dict], current_time,
) -> Tuple[str, int, str]:
    """
    Compute time status by analyzing the full remaining schedule chain.

    Returns: (status, total_slack_minutes, message)
    """
    if not remaining:
        return 'ON_TRACK', 0, 'All done.'

    first = remaining[0]
    first_start = first['scheduled_time']
    minutes_until_first = _minutes_between(current_time, first_start)

    # Walk the schedule chain to compute total slack
    total_slack = 0
    cursor_time = current_time

    for i, item in enumerate(remaining):
        item_start = item['scheduled_time']
        item_duration = item['duration_minutes']

        # Slack before this item = scheduled_start - when we'd actually start
        gap = _minutes_between(cursor_time, item_start)
        if gap > 0:
            total_slack += gap

        # After this item, cursor moves to end of item
        # (either from scheduled start or from cursor, whichever is later)
        actual_start_minutes = max(
            _time_to_minutes(item_start),
            _time_to_minutes(cursor_time),
        )
        end_minutes = actual_start_minutes + item_duration
        cursor_time = _minutes_to_time(min(end_minutes, 23 * 60 + 59))

    # Determine status
    if minutes_until_first >= BUFFER_WARNING_MINUTES:
        # Plenty of time before first item
        status = 'ON_TRACK'
        message = f"You're on track. {first['name']} is at {first_start.strftime('%I:%M %p').lstrip('0')}."
    elif total_slack >= BUFFER_WARNING_MINUTES:
        # Some items may be past scheduled time, but slack absorbs it
        status = 'USING_BUFFER'
        message = (
            f"You're using buffer time. "
            f"{first['name']} is at {first_start.strftime('%I:%M %p').lstrip('0')} "
            f"— about {total_slack} minutes of slack remaining."
        )
    else:
        # Slack exhausted — can't complete on time
        status = 'LATE'
        message = (
            f"You're running behind on {first['name']}. "
            f"Want to adjust the schedule?"
        )

    return status, total_slack, message


def _minutes_between(t1, t2) -> int:
    """Minutes from t1 to t2 (positive if t2 is later)."""
    return _time_to_minutes(t2) - _time_to_minutes(t1)


def _time_to_minutes(t) -> int:
    """Convert a time object to minutes since midnight."""
    return t.hour * 60 + t.minute


def _minutes_to_time(minutes: int):
    """Convert minutes since midnight to a time object."""
    from datetime import time
    h = min(23, minutes // 60)
    m = minutes % 60
    return time(h, m)
