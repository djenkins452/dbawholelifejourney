"""
Authoritative Today Execution Contract.

Single source of truth for "what actionable things exist today, what state are
they in, and what is the next right one to do?"

ARCHITECTURAL RULES:
  1. Atomic execution items only: Task, RoutineItem, MedicationDose.
     Summary objects (routine containers, med windows, domain summaries) go in
     'summaries', never in 'items'.
  2. Items include ONLY: overdue tasks, today tasks, today routine items,
     today medication doses. Not broad unscheduled backlog.
  3. Binary domains (journal, workout, faith) appear in summaries.domains
     only if explicit canonical today-truth exists.
  4. Each item has grouping metadata (execution_group_type, execution_group_id)
     so consumers can group without promoting summaries to action units.

CONSUMERS:
  - Dashboard V2: calls build_today_execution() directly (live, 30s cache)
  - SAE: calls during rebuild → stores in UserState → CoS reads from SAE
  - CoS: reads via get_module_state(user, 'execution')
  - Both feed items into build_action_priorities() for ordering
"""

import logging

from django.urls import reverse

from apps.core.utils import classify_time_status, get_user_now, get_user_today

logger = logging.getLogger(__name__)


def build_today_execution(user):
    """
    Build the authoritative execution contract for today.

    Returns:
        dict with 'items' (atomic ExecutionItem dicts) and 'summaries'.
    """
    user_now = get_user_now(user)
    user_today = get_user_today(user)

    items = []
    summaries = {
        'routines': {},
        'medications': {},
        'domains': {},
        'tasks_completed_today': 0,
    }

    # ── Tasks (overdue + due today, excluding legacy routine tasks) ──
    try:
        items.extend(_collect_task_items(user, user_now, user_today))
    except Exception:
        logger.warning("Execution contract: task collection failed", exc_info=True)

    # ── Task completion count ──
    try:
        from apps.life.models import Task
        summaries['tasks_completed_today'] = Task.objects.filter(
            user=user, completion_status='completed',
            completed_at__date=user_today,
        ).count()
    except Exception:
        pass

    # ── Routine items (applicable for today) ──
    try:
        routine_items, routine_summaries = _collect_routine_items(user, user_now, user_today)
        items.extend(routine_items)
        summaries['routines'] = routine_summaries
    except Exception:
        logger.warning("Execution contract: routine collection failed", exc_info=True)

    # ── Medication doses (due today) ──
    try:
        med_items, med_summaries = _collect_medication_items(user, user_now, user_today)
        items.extend(med_items)
        summaries['medications'] = med_summaries
    except Exception:
        logger.warning("Execution contract: medication collection failed", exc_info=True)

    # ── Domain summaries (explicit today-truth only) ──
    try:
        summaries['domains'] = _collect_domain_summaries(user, user_today)
    except Exception:
        logger.warning("Execution contract: domain summary failed", exc_info=True)

    return {
        'items': items,
        'summaries': summaries,
    }


# ── Item Collectors ──────────────────────────────────────────────


def _collect_task_items(user, user_now, user_today):
    """Collect overdue + today tasks as ExecutionItems."""
    from apps.life.services.task_queries import TaskQueries

    items = []

    # Overdue tasks (due_date < today)
    for t in TaskQueries.overdue(user, as_of=user_today)[:25]:
        ts = classify_time_status(t.due_date, t.scheduled_time, user_now,
                                  grace_minutes=getattr(t, 'grace_minutes', 0))
        items.append(_task_to_item(t, ts, 'overdue'))

    # Today tasks (due_date == today)
    for t in TaskQueries.due_today(user, as_of=user_today)[:25]:
        if t.is_routine:
            continue  # Legacy routine tasks excluded — use canonical routines
        ts = classify_time_status(t.due_date, t.scheduled_time, user_now,
                                  grace_minutes=getattr(t, 'grace_minutes', 0))
        items.append(_task_to_item(t, ts, ts['status']))

    return items


def _task_to_item(task, time_result, time_status):
    """Convert a Task model instance to an ExecutionItem dict."""
    completed = task.completion_status == 'completed'
    try:
        detail_url = task.get_absolute_url()
    except Exception:
        detail_url = ''
    return {
        'source_type': 'task',
        'source_id': task.id,
        'title': task.title,
        'domain': getattr(task, 'module', '') or 'life',
        'importance': task.commitment_level or 'important',
        'time_status': time_status,
        'scheduled_time': (
            task.scheduled_time.strftime('%H:%M') if task.scheduled_time else None
        ),
        'grace_minutes': getattr(task, 'grace_minutes', 0),
        'completion_status': task.completion_status,
        'completed_today': completed,
        'is_actionable': task.completion_status == 'pending',
        'is_foundational': (
            getattr(task, '_domain_foundational', False)
            or getattr(task, 'is_foundational', False)
            or task.commitment_level == 'foundational'
        ),
        'toggle_url': '',  # Tasks completed via task detail page
        'detail_url': detail_url,
        'execution_group_type': 'standalone',
        'execution_group_id': None,
        'parent_title': None,
    }


def _collect_routine_items(user, user_now, user_today):
    """Collect today's routine items as ExecutionItems + routine summaries."""
    from apps.life.services._routine_internal import get_todays_routine_items

    result = get_todays_routine_items(user)
    items = []
    routine_summaries = result.get('routine_completion', {})

    for window_items in result.get('items_by_window', {}).values():
        for item in window_items:
            status = item.get('status', 'pending')
            completed = status == 'completed'
            importance = item.get('importance', 'flexible')
            schedule_id = item['schedule_id']

            # Derive time_status from the canonical classifier
            # For rescheduled items, use the rescheduled time
            sched_time_str = item.get('scheduled_time')
            rescheduled_time_str = item.get('rescheduled_time')
            sched_time_obj = None
            if sched_time_str:
                try:
                    from datetime import datetime as _dt
                    sched_time_obj = _dt.strptime(
                        sched_time_str.strip(), '%I:%M %p'
                    ).time()
                except (ValueError, AttributeError):
                    pass

            # For rescheduled items: classify against the new time
            if status == 'rescheduled':
                ts = classify_time_status(
                    user_today, sched_time_obj, user_now,
                    grace_minutes=0,
                )
                # Rescheduled items stay actionable until day close
                # — never auto-convert to missed same-day
                time_status = ts['status']
            elif status in ('missed', 'overdue'):
                time_status = 'overdue'
            else:
                ts = classify_time_status(
                    user_today, sched_time_obj, user_now,
                    grace_minutes=0,
                )
                time_status = ts['status']

            items.append({
                'source_type': 'routine_item',
                'source_id': schedule_id,
                'title': item.get('item_name', ''),
                'domain': 'life',
                'importance': importance,
                'time_status': time_status,
                'scheduled_time': (
                    sched_time_obj.strftime('%H:%M') if sched_time_obj else None
                ),
                'grace_minutes': 0,
                'completion_status': status,
                'completed_today': completed,
                'is_actionable': status in ('pending', 'missed', 'overdue', 'rescheduled'),
                'is_foundational': importance == 'foundational',
                'rescheduled_time': rescheduled_time_str,
                'reschedule_count': item.get('reschedule_count', 0),
                'toggle_url': reverse(
                    'life:routine_toggle'
                ),
                'detail_url': reverse('life:routine_list'),
                'execution_group_type': 'routine',
                'execution_group_id': item.get('routine_id'),
                'parent_title': item.get('routine_name', ''),
            })

    return items, routine_summaries


def _collect_medication_items(user, user_now, user_today):
    """Collect today's medication dose instances as ExecutionItems + window summaries."""
    from apps.core.ai_state.state_builder import build_medicine_state

    med_state = build_medicine_state(user)
    schedule_status = med_state.get('schedule_status_today', [])
    items = []
    window_summaries = {}

    for entry in schedule_status:
        status = entry.get('status', 'upcoming')
        completed = status in ('taken',)
        window = entry.get('window_label', 'unscheduled')

        # Build window summary
        if window not in window_summaries:
            window_summaries[window] = {
                'total': 0, 'taken': 0, 'all_taken': False,
                'label': window.replace('_', ' ').title() + ' Stack',
            }
        window_summaries[window]['total'] += 1
        if completed:
            window_summaries[window]['taken'] += 1

        # Map medication status to execution status
        if status == 'taken':
            exec_status = 'completed'
        elif status == 'missed':
            exec_status = 'missed'
        elif status == 'overdue':
            exec_status = 'overdue'
        else:
            exec_status = 'upcoming'

        items.append({
            'source_type': 'medication_dose',
            'source_id': hash(f"{entry.get('medicine_name')}_{window}_{entry.get('scheduled_time')}"),
            'title': entry.get('medicine_name', 'Medication'),
            'domain': 'health',
            'importance': 'foundational',  # Medications are always foundational
            'time_status': exec_status if exec_status in ('upcoming', 'overdue') else 'upcoming',
            'scheduled_time': entry.get('scheduled_time'),
            'grace_minutes': 0,
            'completion_status': exec_status,
            'completed_today': completed,
            'is_actionable': not completed and status != 'missed',
            'is_foundational': True,
            'toggle_url': '',  # Medications logged via health module
            'detail_url': '',
            'execution_group_type': 'medication_window',
            'execution_group_id': window,
            'parent_title': window_summaries[window]['label'],
        })

    # Finalize window summaries
    for ws in window_summaries.values():
        ws['all_taken'] = ws['taken'] >= ws['total'] and ws['total'] > 0

    return items, window_summaries


def _collect_domain_summaries(user, user_today):
    """Collect binary domain completion (explicit today-truth only)."""
    domains = {}

    try:
        from apps.journal.models import JournalEntry
        domains['journal'] = JournalEntry.objects.filter(
            user=user, entry_date=user_today,
        ).exists()
    except Exception:
        domains['journal'] = False

    try:
        from apps.health.models import WorkoutSession
        domains['workout'] = WorkoutSession.objects.filter(
            user=user, date=user_today,
        ).exclude(status='deleted').exists()
    except Exception:
        domains['workout'] = False

    try:
        from apps.faith.engagement import get_faith_engagement_details
        faith = get_faith_engagement_details(user, user_today)
        domains['bible_reading'] = faith.get('reading_completed_today', False)
        domains['prayer'] = faith.get('faith_task_completed_today', False)
        domains['faith_engaged'] = faith.get('faith_engaged_today', False)
    except Exception:
        domains['bible_reading'] = False
        domains['prayer'] = False
        domains['faith_engaged'] = False

    return domains
