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

    # Use centralized time classification for missed detection
    from apps.core.utils import classify_time_status

    # ── Batch-fetch source objects for traceability display ──
    # Collect source_object_ids by completion_source type, then fetch
    # in bulk to avoid N+1 queries.
    _source_ids_by_type = {}  # {'workout': {42, 55}, 'journal': {10}}
    for _, item in today_items:
        log = log_by_schedule.get(item.id)
        if log and getattr(log, 'completion_source', 'manual') != 'manual':
            src = log.completion_source
            oid = getattr(log, 'source_object_id', None)
            if oid:
                _source_ids_by_type.setdefault(src, set()).add(oid)

    _source_objects = {}  # (type, id) → display dict
    if 'workout' in _source_ids_by_type:
        try:
            from apps.health.models import WorkoutSession
            for ws in WorkoutSession.objects.filter(
                pk__in=_source_ids_by_type['workout']
            ).only('id', 'name', 'workout_type', 'started_at', 'completed_at'):
                display_name = ws.name or ws.workout_type or 'Workout'
                display_time = ws.started_at or ws.completed_at
                _source_objects[('workout', ws.pk)] = {
                    'name': display_name,
                    'time': display_time,
                }
        except Exception:
            pass  # Graceful degradation — fall back to generic label

    if 'journal' in _source_ids_by_type:
        try:
            from apps.journal.models import JournalEntry
            for je in JournalEntry.objects.filter(
                pk__in=_source_ids_by_type['journal']
            ).only('id', 'title', 'created_at'):
                _source_objects[('journal', je.pk)] = {
                    'name': je.title or 'Journal Entry',
                    'time': je.created_at,
                }
        except Exception:
            pass

    for routine, item in today_items:
        log = log_by_schedule.get(item.id)
        display_time = item.scheduled_time  # may be overridden by reschedule
        rescheduled_time = None

        reschedule_count = 0

        if log:
            if log.log_status in ('completed', 'completed_late'):
                status = 'completed'
                total_completed += 1
            elif log.log_status == 'skipped':
                status = 'skipped'
            elif log.log_status == 'rescheduled':
                # Same-day reschedule: use rescheduled_time, item stays
                # actionable until day close (never auto-missed same-day)
                rescheduled_time = getattr(log, 'rescheduled_time', None)
                display_time = rescheduled_time or item.scheduled_time
                reschedule_count = getattr(log, 'reschedule_count', 0) or 0
                status = 'rescheduled'
            else:
                status = 'pending'
        else:
            # Grace-aware overdue detection via centralized function
            result = classify_time_status(
                user_today, item.scheduled_time, user_now,
                grace_minutes=item.grace_period_minutes or 0,
            )
            if result['status'] == 'overdue':
                # Same-day: show as 'overdue' (still actionable).
                # 'missed' is a post-day-close outcome only.
                status = 'overdue'
                total_missed += 1
            else:
                status = 'pending'

        # Completion source + traceability
        completion_source = getattr(log, 'completion_source', 'manual') if log else None
        source_object_id = getattr(log, 'source_object_id', None) if log else None

        # Build contextual completion-via label for activity-driven completions.
        # Uses batch-fetched source objects for rich display:
        #   "Completed via Back + Arms at 6:42 AM" (workout with name)
        #   "Completed via Workout at 6:42 AM" (workout without name)
        #   "Completed via Journal Entry at 8:15 PM" (journal)
        completion_via_label = None
        source_display_name = None
        source_display_time = None
        if completion_source and completion_source != 'manual':
            src_obj = _source_objects.get((completion_source, source_object_id))
            if src_obj:
                source_display_name = src_obj['name']
                source_display_time = src_obj.get('time')
                time_str = ''
                if source_display_time:
                    try:
                        time_str = f" at {source_display_time.strftime('%I:%M %p').lstrip('0')}"
                    except Exception:
                        pass
                completion_via_label = f"Completed via {source_display_name}{time_str}"
            else:
                # Fallback: generic label from completion_source choices
                time_str = ''
                if log and log.completed_at:
                    try:
                        time_str = f" at {log.completed_at.strftime('%I:%M %p').lstrip('0')}"
                    except Exception:
                        pass
                from apps.life.models import RoutineLog as _RL
                source_label = dict(_RL.COMPLETION_SOURCE_CHOICES).get(
                    completion_source, completion_source.title()
                )
                completion_via_label = f"Completed via {source_label}{time_str}"

        entry = {
            'routine_id': routine.id,
            'routine_name': routine.name,
            'schedule_id': item.id,
            'item_name': item.name,
            'importance': getattr(item, 'importance', 'flexible'),
            'scheduled_time': (
                display_time.strftime('%I:%M %p').lstrip('0')
                if display_time else None
            ),
            'rescheduled_time': (
                rescheduled_time.strftime('%I:%M %p').lstrip('0')
                if rescheduled_time else None
            ),
            'time_of_day': routine.time_of_day,
            'status': status,
            'is_completed': status == 'completed',
            'reschedule_count': reschedule_count,
            'maintenance_logged': getattr(log, 'maintenance_logged', False) if log else False,
            # Completion source tracking
            'completion_source': completion_source,
            'source_object_id': source_object_id,
            'completion_via_label': completion_via_label,
            'source_display_name': source_display_name,
            'source_display_time': (
                source_display_time.strftime('%I:%M %p').lstrip('0')
                if source_display_time else None
            ),
            # Execution truth
            'timing': getattr(log, 'timing', '') if log else '',
            # Routine type (Phase 2: binary vs activity)
            'routine_type': getattr(item, 'routine_type', 'binary'),
            'activity_type': getattr(item, 'activity_type', None),
            # Maintenance bridge config
            'creates_maintenance_log': getattr(item, 'creates_maintenance_log', False),
            'maintenance_type': getattr(item, 'maintenance_type', ''),
            'maintenance_area': getattr(item, 'maintenance_area', ''),
            'default_maintenance_title': getattr(item, 'default_maintenance_title', '') or item.name,
            'follow_up_days': getattr(item, 'follow_up_days', None),
        }

        window = routine.time_of_day or 'other'
        items_by_window.setdefault(window, []).append(entry)

    # Derive per-routine completion from item logs (never stored)
    _routine_items = {}  # routine_id → {total, completed}
    for routine, item in today_items:
        rid = routine.id
        if rid not in _routine_items:
            _routine_items[rid] = {'total': 0, 'completed': 0, 'name': routine.name}
        _routine_items[rid]['total'] += 1
        log = log_by_schedule.get(item.id)
        if log and log.log_status in ('completed', 'completed_late'):
            _routine_items[rid]['completed'] += 1

    routine_completion = {}
    for rid, counts in _routine_items.items():
        routine_completion[rid] = {
            'all_complete': counts['completed'] == counts['total'] and counts['total'] > 0,
            'completed_count': counts['completed'],
            'total_count': counts['total'],
            'name': counts['name'],
        }

    return {
        'items_by_window': items_by_window,
        'today_count': len(today_items),
        'today_completed': total_completed,
        'today_missed': total_missed,
        'current_window': get_current_window(user),
        'logs_by_schedule': log_by_schedule,
        'total_routines': total_routines,
        'routines': list(active_routines),
        'routine_completion': routine_completion,
    }
