"""
Canonical routine domain logic — INTERNAL to state_builder.

This module is the single source of truth for routine state computation
and status transitions. It is called ONLY by:
- apps.core.ai_state.state_builder.build_routine_state()

The UI (RoutineListView) accesses routine state via build_routine_state(),
NOT by calling these functions directly.

Status transition rules (strict execution model):
- One RoutineLog per schedule per day (enforced by unique_together)
- none → completed  (toggle: first check)
- completed → none  (toggle: un-check, deletes log)
- skipped → completed  (toggle: re-check a skipped item)
- none → skipped  (explicit skip action)
- Missed is COMPUTED, not stored (absence of log + time past grace)
- No auto-complete — completion is explicit only
"""

import logging
from datetime import datetime as _dt_cls, timedelta as _td

from django.utils import timezone

from apps.core.time_windows import (
    WINDOW_DISPLAY_NAMES,
    WINDOW_HOURS,
    WINDOW_ORDER,
    get_current_window,
)
from apps.core.utils import get_user_now, get_user_today

logger = logging.getLogger(__name__)


def _get_todays_routine_items(user):
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


# ── Status Transition Service Functions ────────────────────────────
# These are the ONLY way to mutate RoutineLog state. Views call these,
# not raw ORM operations.


def toggle_routine_completion(user, schedule, target_date):
    """
    Toggle a routine schedule item's completion for a date.

    Transition rules:
        no log → completed (create)
        completed/completed_late → pending (delete log)
        skipped → completed (update)

    Args:
        user: User instance
        schedule: RoutineSchedule instance (must belong to user)
        target_date: date

    Returns:
        dict: {status: str, is_completed: bool}
    """
    from apps.life.models import RoutineLog

    existing_log = RoutineLog.objects.filter(
        schedule=schedule, scheduled_date=target_date,
    ).first()

    if existing_log:
        if existing_log.log_status in ('completed', 'completed_late'):
            # Un-complete: remove the log entirely
            existing_log.delete()
            return {'status': 'pending', 'is_completed': False}
        elif existing_log.log_status == 'skipped':
            # Convert skip → completed
            existing_log.log_status = 'completed'
            existing_log.completed_at = timezone.now()
            existing_log.save(update_fields=['log_status', 'completed_at', 'updated_at'])
            return {'status': 'completed', 'is_completed': True}
        else:
            return {'status': existing_log.log_status, 'is_completed': False}
    else:
        # No log → create completed
        RoutineLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=target_date,
            log_status='completed',
            completed_at=timezone.now(),
        )
        return {'status': 'completed', 'is_completed': True}


def skip_routine(user, schedule, target_date):
    """
    Mark a routine schedule item as skipped for a date.

    Uses update_or_create to prevent duplicates (defense-in-depth
    alongside unique_together DB constraint).

    Args:
        user: User instance
        schedule: RoutineSchedule instance (must belong to user)
        target_date: date

    Returns:
        dict: {status: 'skipped'}
    """
    from apps.life.models import RoutineLog

    RoutineLog.objects.update_or_create(
        schedule=schedule,
        scheduled_date=target_date,
        defaults={
            'user': user,
            'log_status': 'skipped',
            'completed_at': None,
        },
    )
    return {'status': 'skipped'}
