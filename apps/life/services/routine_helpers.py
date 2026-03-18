"""
Canonical routine helpers — shared logic for routine state computation.

Extracted from apps.core.ai_state.state_builder.build_routine_state() to
provide a single source of truth for window grouping, current window
detection, and today's routine item collection.

Used by:
- RoutineListView (UI layer)
- build_routine_state (intelligence layer)
"""

import logging
from datetime import datetime as _dt_cls, timedelta as _td

from apps.core.utils import get_user_now, get_user_today

logger = logging.getLogger(__name__)

# Canonical time window boundaries (hour ranges, inclusive start, exclusive end)
WINDOW_HOURS = {
    'morning': (5, 10),
    'mid_morning': (10, 12),
    'lunch': (12, 14),
    'afternoon': (14, 17),
    'evening': (17, 21),
    'nightly': (21, 24),
}

# Display-friendly window names
WINDOW_DISPLAY_NAMES = {
    'morning': 'Morning',
    'mid_morning': 'Mid-Morning',
    'lunch': 'Lunch',
    'afternoon': 'Afternoon',
    'evening': 'Evening',
    'nightly': 'Nightly',
}

# Canonical window ordering for consistent UI display
WINDOW_ORDER = ['morning', 'mid_morning', 'lunch', 'afternoon', 'evening', 'nightly']


def get_current_window(user):
    """
    Determine the current time window based on the user's local time.

    Returns:
        str: Window key (e.g., 'morning', 'afternoon') or 'other' if outside all windows.
    """
    user_now = get_user_now(user)
    hour = user_now.time().hour
    for window_name, (start_h, end_h) in WINDOW_HOURS.items():
        if start_h <= hour < end_h:
            return window_name
    return 'other'


def get_todays_routine_items(user):
    """
    Collect today's routine schedule items for a user, grouped by time window.

    Returns:
        dict with keys:
            items_by_window: {window_key: [item_dicts]}
            today_count: int
            today_completed: int
            today_missed: int
            current_window: str
            logs_by_schedule: {schedule_id: RoutineLog}
    """
    from apps.life.models import Routine, RoutineLog, RoutineSchedule

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()
    weekday = user_today.weekday()  # 0=Monday

    # Active routines with prefetched items
    active_routines = Routine.objects.filter(
        user=user, is_active=True,
    ).prefetch_related('items')

    total_routines = active_routines.count()
    if total_routines == 0:
        return {
            'items_by_window': {},
            'today_count': 0,
            'today_completed': 0,
            'today_missed': 0,
            'current_window': get_current_window(user),
            'logs_by_schedule': {},
            'total_routines': 0,
            'routines': [],
        }

    # Collect today's applicable schedule items
    today_items = []
    for routine in active_routines:
        for item in routine.items.filter(is_active=True):
            if item.specific_date:
                if item.specific_date != user_today:
                    continue
            elif not item.applies_to_day(weekday):
                continue
            today_items.append((routine, item))

    # Batch-fetch today's logs
    schedule_ids = [item.id for _, item in today_items]
    logs = RoutineLog.objects.filter(
        schedule_id__in=schedule_ids,
        scheduled_date=user_today,
    )
    log_by_schedule = {log.schedule_id: log for log in logs}

    # Build structured items grouped by window
    items_by_window = {}
    total_completed = 0
    total_missed = 0

    for routine, item in today_items:
        log = log_by_schedule.get(item.id)
        if log:
            if log.log_status in ('completed', 'completed_late'):
                status = 'completed'
                total_completed += 1
            elif log.log_status == 'skipped':
                status = 'skipped'
            else:
                status = 'pending'
        else:
            # No log = pending or missed (based on time + grace)
            cutoff = item.scheduled_time
            if cutoff and item.grace_period_minutes:
                cutoff_dt = _dt_cls.combine(user_today, cutoff) + _td(
                    minutes=item.grace_period_minutes
                )
                cutoff = cutoff_dt.time()

            if cutoff and current_time > cutoff:
                status = 'missed'
                total_missed += 1
            else:
                status = 'pending'

        entry = {
            'routine_id': routine.id,
            'routine_name': routine.name,
            'schedule_id': item.id,
            'item_name': item.name,
            'scheduled_time': (
                item.scheduled_time.strftime('%I:%M %p').lstrip('0')
                if item.scheduled_time else None
            ),
            'time_of_day': routine.time_of_day,
            'status': status,
            'is_completed': status == 'completed',
        }

        window = routine.time_of_day or 'other'
        items_by_window.setdefault(window, []).append(entry)

    return {
        'items_by_window': items_by_window,
        'today_count': len(today_items),
        'today_completed': total_completed,
        'today_missed': total_missed,
        'current_window': get_current_window(user),
        'logs_by_schedule': log_by_schedule,
        'total_routines': total_routines,
        'routines': list(active_routines),
    }
