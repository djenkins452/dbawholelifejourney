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

    # Fetch execution truth once — used for dependency gating (routine + domain
    # prerequisites resolve via truth) and for domain summaries further below.
    # Kept as a single call to avoid redundant work.
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, user_today)
    except Exception:
        logger.warning(
            "Execution contract: truth fetch failed (gating will fail open)",
            exc_info=True,
        )
        truth = {}

    items = []
    summaries = {
        'routines': {},
        'medications': {},
        'domains': {},
        'tasks_completed_today': 0,
    }

    # ── Tasks (overdue + due today, excluding legacy routine tasks) ──
    try:
        items.extend(_collect_task_items(user, user_now, user_today, truth))
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
        summaries['domains'], summaries['expected'] = _collect_domain_summaries(user, user_today)
    except Exception:
        logger.warning("Execution contract: domain summary failed", exc_info=True)

    # Annotate every item with task_class / recovery_grace_minutes /
    # is_reset_action. PURE annotation — additive fields only.
    try:
        from apps.core.execution.task_classifier import annotate as _annotate
        for it in items:
            _annotate(it)
    except Exception:
        logger.warning(
            "Execution contract: classifier annotation failed",
            exc_info=True,
        )

    return {
        'items': items,
        'summaries': summaries,
    }


# ── Item Collectors ──────────────────────────────────────────────


def _collect_task_items(user, user_now, user_today, truth=None):
    """Collect overdue + today tasks as ExecutionItems.

    Dependency-blocked tasks are excluded via the shared is_task_blocked()
    helper so they never enter the execution contract — and therefore never
    reach the action prioritizer, `facts['next_action']`, the CoS locked
    fact statements, or dashboard item lists.
    """
    from apps.core.execution.dependency_gating import is_task_blocked
    from apps.life.services.task_queries import TaskQueries

    items = []

    # Overdue tasks (due_date < today)
    for t in TaskQueries.overdue(user, as_of=user_today)[:25]:
        if is_task_blocked(t, truth):
            continue
        ts = classify_time_status(t.due_date, t.scheduled_time, user_now,
                                  grace_minutes=getattr(t, 'grace_minutes', 0))
        items.append(_task_to_item(t, ts, 'overdue'))

    # Today tasks (due_date == today)
    for t in TaskQueries.due_today(user, as_of=user_today)[:25]:
        if t.is_routine:
            continue  # Legacy routine tasks excluded — use canonical routines
        if is_task_blocked(t, truth):
            continue
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
    try:
        toggle_url = reverse(
            'dashboard_v2:task_toggle',
            kwargs={'pk': task.id},
        )
    except Exception:
        toggle_url = ''
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
        'toggle_url': toggle_url,
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
                    'dashboard_v2:routine_schedule_toggle',
                    kwargs={'schedule_id': schedule_id},
                ),
                'detail_url': reverse('life:routine_list'),
                'execution_group_type': 'routine',
                'execution_group_id': item.get('routine_id'),
                'parent_title': item.get('routine_name', ''),
                # Activity-type + source tracking (Phase 2.5/3)
                'completion_source': item.get('completion_source'),
                'completion_via_label': item.get('completion_via_label'),
                'routine_type': item.get('routine_type', 'binary'),
                'activity_type': item.get('activity_type'),
            })

    return items, routine_summaries


def _normalize_time_to_24h(time_str):
    """Normalize a time string to HH:MM 24-hour format.

    Handles:
    - '8:00 AM', '12:30 PM' (12-hour with AM/PM from state_builder)
    - '08:00', '14:30' (24-hour, already correct)
    - datetime.time objects (passthrough via strftime)

    Returns HH:MM string or None if unparseable.
    """
    if not time_str:
        return None
    # If it's already a time object, format directly
    if hasattr(time_str, 'strftime'):
        return time_str.strftime('%H:%M')
    time_str = str(time_str).strip()
    from datetime import datetime as _dt
    # Try 12-hour format first (most common from state_builder)
    for fmt in ('%I:%M %p', '%H:%M'):
        try:
            return _dt.strptime(time_str, fmt).strftime('%H:%M')
        except ValueError:
            continue
    return None


def _collect_medication_items(user, user_now, user_today):
    """Collect today's medication dose instances as ExecutionItems + window summaries."""
    from apps.core.ai_state.state_builder import build_medicine_state
    from apps.core.time_windows import WINDOW_DISPLAY_NAMES

    med_state = build_medicine_state(user)
    schedule_status = med_state.get('schedule_status_today', [])
    items = []
    window_summaries = {}

    for entry in schedule_status:
        status = entry.get('status', 'upcoming')
        completed = status in ('taken',)
        window = entry.get('window_label', 'unscheduled')
        intake_type = entry.get('intake_type', 'medication')
        priority = entry.get('priority', 'critical')
        is_supplement = (intake_type == 'supplement')

        # Determine group type and label based on intake_type
        if is_supplement:
            group_type = 'supplement_window'
            label_suffix = ' Supplements'
        else:
            group_type = 'medication_window'
            label_suffix = ' Medications'

        # Window summary key includes group_type to keep meds/supplements separate
        summary_key = f"{group_type}_{window}"

        # Build window summary with canonical display names
        if summary_key not in window_summaries:
            display_name = WINDOW_DISPLAY_NAMES.get(window, window.replace('_', ' ').title())
            window_summaries[summary_key] = {
                'total': 0, 'taken': 0, 'all_taken': False,
                'label': display_name + label_suffix,
            }
        window_summaries[summary_key]['total'] += 1
        if completed:
            window_summaries[summary_key]['taken'] += 1

        # Map medication status to execution status
        if status == 'taken':
            exec_status = 'completed'
        elif status == 'missed':
            exec_status = 'missed'
        elif status == 'overdue':
            # Supplements with optimization priority don't escalate to overdue
            if is_supplement and priority == 'optimization':
                exec_status = 'upcoming'
            else:
                exec_status = 'overdue'
        else:
            exec_status = 'upcoming'

        # Importance driven by priority, not intake_type
        is_foundational = (priority == 'critical')
        importance = 'foundational' if is_foundational else 'standard'

        # Build toggle URL for individual dose completion
        schedule_id = entry.get('schedule_id')
        medicine_id = entry.get('medicine_id')
        toggle_url = ''
        if schedule_id:
            try:
                toggle_url = reverse(
                    'dashboard_v2:intake_log',
                    kwargs={'schedule_id': schedule_id},
                )
            except Exception:
                pass

        # Build detail URL linking to medicine detail page
        detail_url = ''
        if medicine_id:
            try:
                detail_url = reverse(
                    'health:intake_detail',
                    kwargs={'pk': medicine_id},
                )
            except Exception:
                pass

        # Normalize scheduled_time to HH:MM 24-hour format.
        # state_builder produces '8:00 AM' format; the action prioritizer
        # and grouped action center require 'HH:MM'. Without this, _parse_time
        # returns None and the item falls into the flexible bucket incorrectly.
        normalized_time = _normalize_time_to_24h(entry.get('scheduled_time'))

        items.append({
            'source_type': 'medication_dose' if not is_supplement else 'supplement_dose',
            'source_id': schedule_id or hash(f"{entry.get('medicine_name')}_{window}_{entry.get('scheduled_time')}"),
            'title': entry.get('medicine_name', 'Supplement' if is_supplement else 'Medication'),
            'domain': 'health',
            'importance': importance,
            'time_status': exec_status if exec_status in ('upcoming', 'overdue') else 'upcoming',
            'scheduled_time': normalized_time,
            'grace_minutes': 0,
            'completion_status': exec_status,
            'completed_today': completed,
            'is_actionable': not completed and status != 'missed',
            'is_foundational': is_foundational,
            'toggle_url': toggle_url,
            'detail_url': detail_url,
            'execution_group_type': group_type,
            'execution_group_id': window,
            'parent_title': window_summaries[summary_key]['label'],
            'intake_type': intake_type,
            'priority': priority,
        })

    # Finalize window summaries
    for ws in window_summaries.values():
        ws['all_taken'] = ws['taken'] >= ws['total'] and ws['total'] > 0

    return items, window_summaries


def _collect_domain_summaries(user, user_today):
    """
    Collect binary domain completion AND expected flags using the
    Execution Truth Engine.

    CRITICAL: This delegates to the single source of truth. It does NOT
    query models directly. The engine handles cross-domain bridges
    (e.g., routine "Prayer Time" → faith.prayer_completed).

    Returns:
        (domains_dict, expected_dict) — completion status and expectation flags.
    """
    domains = {}
    expected = {}

    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, user_today)

        faith = truth['domains']['faith']
        domains['prayer'] = faith['prayer_completed']
        domains['bible_reading'] = faith['bible_reading_completed']
        domains['faith_engaged'] = faith['prayer_completed'] or faith['bible_reading_completed']

        domains['workout'] = truth['domains']['workout']['completed']
        domains['journal'] = truth['domains']['journal']['completed']

        # Expected flags — only expected domains get included in prioritizer
        expected['faith'] = faith.get('prayer_expected', False) or faith.get('bible_expected', False)
        expected['workout'] = truth['domains']['workout'].get('expected', False)
        expected['journal'] = truth['domains']['journal'].get('expected', False)
    except Exception:
        logger.warning("Domain summaries: execution truth unavailable", exc_info=True)
        domains['bible_reading'] = False
        domains['prayer'] = False
        domains['faith_engaged'] = False
        domains['workout'] = False
        domains['journal'] = False

    return domains, expected
