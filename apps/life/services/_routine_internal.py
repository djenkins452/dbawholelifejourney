"""
INTERNAL routine state computation — DO NOT IMPORT OUTSIDE ALLOWED LAYERS.

This module is private to the routine domain. Allowed callers:
  - apps.core.ai_state.state_builder (builds canonical _contract)
  - apps.life.services.routine_helpers (public service interface)

NO views, templates, or other services should import from this module.
If you need routine data in the UI, use build_routine_state().
If you need to mutate routine state, use routine_helpers.toggle_routine_completion()
or routine_helpers.skip_routine().
"""

import logging
from datetime import datetime as _dt_cls, timedelta as _td

from apps.core.time_windows import get_current_window
from apps.core.utils import get_user_now, get_user_today

logger = logging.getLogger(__name__)


def get_todays_routine_items(user):
    """
    Collect today's routine schedule items for a user, grouped by time window.

    INTERNAL — called by build_routine_state() only.

    Returns:
        dict with keys:
            items_by_window: {window_key: [item_dicts]}
            today_count: int
            today_completed: int
            today_missed: int
            current_window: str
            logs_by_schedule: {schedule_id: RoutineLog}
            total_routines: int
            routines: list of Routine objects
    """
    from apps.life.models import Routine, RoutineLog

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()
    weekday = user_today.weekday()  # 0=Monday

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

    today_items = []
    for routine in active_routines:
        for item in routine.items.filter(is_active=True):
            if item.specific_date:
                if item.specific_date != user_today:
                    continue
            elif not item.applies_to_day(weekday):
                continue
            today_items.append((routine, item))

    schedule_ids = [item.id for _, item in today_items]
    logs = RoutineLog.objects.filter(
        schedule_id__in=schedule_ids,
        scheduled_date=user_today,
    )
    log_by_schedule = {log.schedule_id: log for log in logs}

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
