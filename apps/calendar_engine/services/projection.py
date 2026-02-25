"""
Projection Service — Projects Tasks, Goals, Habits onto CalendarEvents.

Source items remain the source of truth. CalendarEvent is the time interface.
All time changes are logged to the unified ExecutionLog via DriftEngine.
"""

import datetime as dt
import logging

from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent, RecurrenceRule
from apps.calendar_engine.utils.idempotency import compute_idempotency_key

logger = logging.getLogger(__name__)


def _log_schedule_change(user, event, old_start, new_start):
    """Log a schedule time change to the unified ExecutionLog."""
    if old_start == new_start:
        return
    try:
        from apps.core.drift.engine import DriftEngine
        DriftEngine.record_schedule_change(user, event, old_start, new_start)
    except Exception as e:
        logger.debug("Drift logging skipped for event %s: %s", event.pk, e)


def _get_default_domain(slug='work'):
    """Get a LifeDomain by slug, or None if not found."""
    from apps.purpose.models import LifeDomain
    return LifeDomain.objects.filter(slug=slug, is_active=True).first()


def _resolve_domain_for_task(task):
    """
    Derive domain from task context.
    Routine tasks get domain based on title keywords.
    Regular tasks default to Work.
    """
    if getattr(task, 'is_routine', False):
        title_lower = task.title.lower()
        _ROUTINE_DOMAIN_MAP = {
            'faith': [
                'quiet time', 'bible', 'prayer', 'devotional',
                'scripture', 'reading plan',
            ],
            'health': [
                'workout', 'exercise', 'run', 'gym', 'walk',
                'stretch', 'yoga', 'swim', 'cardio',
            ],
        }
        for slug, keywords in _ROUTINE_DOMAIN_MAP.items():
            if any(kw in title_lower for kw in keywords):
                domain = _get_default_domain(slug)
                if domain:
                    return domain
    return _get_default_domain('work')


def _resolve_domain_for_goal(goal):
    """Use goal's domain if set, else default to Work."""
    if goal.domain_id:
        return goal.domain
    return _get_default_domain('work')


def _resolve_domain_for_habit(habit):
    """Use habit's domain if set, else map category or default to Health."""
    if habit.domain_id:
        return habit.domain
    # HabitGoal.category is a free-text field; try mapping common values
    category_domain_map = {
        'health': 'health',
        'fitness': 'health',
        'faith': 'faith',
        'spiritual': 'faith',
        'family': 'family',
        'work': 'work',
        'finance': 'finances',
    }
    if habit.category:
        slug = category_domain_map.get(habit.category.lower())
        if slug:
            domain = _get_default_domain(slug)
            if domain:
                return domain
    return _get_default_domain('health')


# ──────────────────────────────────────────────────────────
# Task projections
# ──────────────────────────────────────────────────────────

def upsert_from_task(task):
    """
    Ensure a DEADLINE_MARKER exists for a task with a due_date.
    Updates if task date changed; deletes if task has no due_date.
    Routine tasks with scheduled_time are routed to upsert_from_routine_task().
    """
    # Routine tasks get time-specific execution blocks, not deadline markers
    if getattr(task, 'is_routine', False) and task.scheduled_time:
        return upsert_from_routine_task(task)

    existing = CalendarEvent.objects.filter(
        user=task.user,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
    ).first()

    if not task.due_date:
        # No due date — remove any existing marker
        if existing:
            existing.delete()
        return None

    # Build start/end datetimes (deadline markers are all-day by default)
    start_dt = timezone.make_aware(
        dt.datetime.combine(task.due_date, dt.time(23, 59)),
        timezone.get_current_timezone(),
    )
    end_dt = start_dt + dt.timedelta(minutes=1)

    domain = _resolve_domain_for_task(task)

    if existing:
        old_start = existing.start_dt
        existing.title = f"Due: {task.title}"
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.is_all_day = True
        if task.is_completed:
            existing.status = CalendarEvent.STATUS_COMPLETED
        else:
            existing.status = CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(task.user, existing, old_start, start_dt)
        return existing

    task_title = f"Due: {task.title}"
    return CalendarEvent.objects.create(
        user=task.user,
        title=task_title,
        start_dt=start_dt,
        end_dt=end_dt,
        is_all_day=True,
        domain=domain,
        event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        status=CalendarEvent.STATUS_COMPLETED if task.is_completed else CalendarEvent.STATUS_SCHEDULED,
        idempotency_key=compute_idempotency_key(
            task.user_id, task_title, start_dt, end_dt=end_dt,
            source_type='task', source_id=str(task.pk),
        ),
    )


def upsert_from_routine_task(task):
    """
    Create/update a time-specific EXECUTION_BLOCK for a routine task.

    Unlike upsert_from_task() which creates deadline markers at 23:59,
    this creates actual time blocks at the task's scheduled_time with
    proper duration — so the event appears at the right time on the calendar.

    Args:
        task: Task instance with is_routine=True, scheduled_time, due_date

    Returns:
        CalendarEvent instance, or None if missing required fields
    """
    if not task.due_date or not task.scheduled_time:
        return None

    # Look for existing execution block for this task
    existing = CalendarEvent.objects.filter(
        user=task.user,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
    ).first()

    # Build time-specific datetime using user's timezone
    from zoneinfo import ZoneInfo
    user_tz = ZoneInfo(task.user.preferences.timezone_iana)
    start_dt = timezone.make_aware(
        dt.datetime.combine(task.due_date, task.scheduled_time),
        user_tz,
    )
    # Use explicit end time if set, otherwise fall back to duration calculation
    if task.scheduled_end_time:
        end_dt = timezone.make_aware(
            dt.datetime.combine(task.due_date, task.scheduled_end_time),
            user_tz,
        )
    else:
        duration = task.estimated_duration_minutes or 30
        end_dt = start_dt + dt.timedelta(minutes=duration)

    domain = _resolve_domain_for_task(task)
    status = (
        CalendarEvent.STATUS_COMPLETED if task.is_completed
        else CalendarEvent.STATUS_SCHEDULED
    )

    if existing:
        old_start = existing.start_dt
        existing.title = task.title
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.is_all_day = False
        existing.status = status
        existing.save()
        _log_schedule_change(task.user, existing, old_start, start_dt)
        return existing

    return CalendarEvent.objects.create(
        user=task.user,
        title=task.title,
        start_dt=start_dt,
        end_dt=end_dt,
        is_all_day=False,
        domain=domain,
        event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        status=status,
        idempotency_key=compute_idempotency_key(
            task.user_id, task.title, start_dt, end_dt=end_dt,
            source_type='task', source_id=str(task.pk),
        ),
    )


def upsert_execution_block_for_task(task, start_dt, end_dt):
    """
    Create an EXECUTION_BLOCK linked to a task.
    Does not overwrite deadline markers.
    """
    domain = _resolve_domain_for_task(task)
    exec_title = f"Work on: {task.title}"
    return CalendarEvent.objects.create(
        user=task.user,
        title=exec_title,
        start_dt=start_dt,
        end_dt=end_dt,
        domain=domain,
        event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        idempotency_key=compute_idempotency_key(
            task.user_id, exec_title, start_dt, end_dt=end_dt,
            source_type='task', source_id=str(task.pk),
        ),
    )


def delete_task_events(task):
    """Remove all calendar events projected from a task."""
    CalendarEvent.objects.filter(
        user=task.user,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
    ).delete()


# ──────────────────────────────────────────────────────────
# Goal projections
# ──────────────────────────────────────────────────────────

def upsert_from_goal(goal):
    """
    Create/update DEADLINE_MARKER for goal target_date.
    Also creates markers for milestones with target_dates.
    """
    events = []

    # Main goal deadline
    if goal.target_date:
        existing = CalendarEvent.objects.filter(
            user=goal.user,
            source_type=CalendarEvent.SOURCE_GOAL,
            source_id=str(goal.pk),
            event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
        ).first()

        start_dt = timezone.make_aware(
            dt.datetime.combine(goal.target_date, dt.time(23, 59)),
            timezone.get_current_timezone(),
        )
        end_dt = start_dt + dt.timedelta(minutes=1)
        domain = _resolve_domain_for_goal(goal)
        is_completed = goal.status == 'completed'

        if existing:
            old_start = existing.start_dt
            existing.title = f"Goal Due: {goal.title}"
            existing.start_dt = start_dt
            existing.end_dt = end_dt
            existing.domain = domain
            existing.is_all_day = True
            existing.status = CalendarEvent.STATUS_COMPLETED if is_completed else CalendarEvent.STATUS_SCHEDULED
            existing.save()
            _log_schedule_change(goal.user, existing, old_start, start_dt)
            events.append(existing)
        else:
            goal_title = f"Goal Due: {goal.title}"
            events.append(CalendarEvent.objects.create(
                user=goal.user,
                title=goal_title,
                start_dt=start_dt,
                end_dt=end_dt,
                is_all_day=True,
                domain=domain,
                event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
                source_type=CalendarEvent.SOURCE_GOAL,
                source_id=str(goal.pk),
                status=CalendarEvent.STATUS_COMPLETED if is_completed else CalendarEvent.STATUS_SCHEDULED,
                idempotency_key=compute_idempotency_key(
                    goal.user_id, goal_title, start_dt, end_dt=end_dt,
                    source_type='goal', source_id=str(goal.pk),
                ),
            ))

    # Milestone markers
    for milestone in goal.milestones.filter(target_date__isnull=False):
        _upsert_milestone_marker(goal, milestone)

    return events


def _upsert_milestone_marker(goal, milestone):
    """Create/update a deadline marker for a goal milestone."""
    existing = CalendarEvent.objects.filter(
        user=goal.user,
        source_type=CalendarEvent.SOURCE_GOAL_MILESTONE,
        source_id=str(milestone.pk),
        event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
    ).first()

    start_dt = timezone.make_aware(
        dt.datetime.combine(milestone.target_date, dt.time(23, 59)),
        timezone.get_current_timezone(),
    )
    end_dt = start_dt + dt.timedelta(minutes=1)
    domain = _resolve_domain_for_goal(goal)

    if existing:
        old_start = existing.start_dt
        existing.title = f"Milestone: {milestone.title}"
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.is_all_day = True
        existing.status = CalendarEvent.STATUS_COMPLETED if milestone.completed else CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(goal.user, existing, old_start, start_dt)
        return existing

    ms_title = f"Milestone: {milestone.title}"
    return CalendarEvent.objects.create(
        user=goal.user,
        title=ms_title,
        start_dt=start_dt,
        end_dt=end_dt,
        is_all_day=True,
        domain=domain,
        event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
        source_type=CalendarEvent.SOURCE_GOAL_MILESTONE,
        source_id=str(milestone.pk),
        status=CalendarEvent.STATUS_COMPLETED if milestone.completed else CalendarEvent.STATUS_SCHEDULED,
        idempotency_key=compute_idempotency_key(
            goal.user_id, ms_title, start_dt, end_dt=end_dt,
            source_type='goal_milestone', source_id=str(milestone.pk),
        ),
    )


def delete_goal_events(goal):
    """Remove all calendar events projected from a goal and its milestones."""
    CalendarEvent.objects.filter(
        user=goal.user,
        source_type=CalendarEvent.SOURCE_GOAL,
        source_id=str(goal.pk),
    ).delete()
    # Also delete milestone markers
    milestone_ids = [str(m.pk) for m in goal.milestones.all()]
    if milestone_ids:
        CalendarEvent.objects.filter(
            user=goal.user,
            source_type=CalendarEvent.SOURCE_GOAL_MILESTONE,
            source_id__in=milestone_ids,
        ).delete()


# ──────────────────────────────────────────────────────────
# Habit projections
# ──────────────────────────────────────────────────────────

def upsert_from_habit(habit):
    """
    Create a recurring CalendarEvent for a HabitGoal.
    Maps frequency_type → RecurrenceRule.
    """
    existing = CalendarEvent.objects.filter(
        user=habit.user,
        source_type=CalendarEvent.SOURCE_HABIT,
        source_id=str(habit.pk),
    ).first()

    if habit.status not in ('active',):
        if existing:
            existing.status = CalendarEvent.STATUS_CANCELED
            existing.save()
        return existing

    domain = _resolve_domain_for_habit(habit)

    # Use habit start_date as the event anchor
    start_dt = timezone.make_aware(
        dt.datetime.combine(habit.start_date, dt.time(8, 0)),  # Default 8am
        timezone.get_current_timezone(),
    )
    # Estimate duration from measurement type
    duration_map = {
        'binary': 30,
        'duration': 60,
        'count': 30,
        'target': 45,
    }
    duration = duration_map.get(habit.measurement_type, 30)
    end_dt = start_dt + dt.timedelta(minutes=duration)

    if existing:
        old_start = existing.start_dt
        existing.title = habit.name
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.is_protected = True
        existing.status = CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(habit.user, existing, old_start, start_dt)
        event = existing
    else:
        event = CalendarEvent.objects.create(
            user=habit.user,
            title=habit.name,
            start_dt=start_dt,
            end_dt=end_dt,
            domain=domain,
            event_kind=CalendarEvent.KIND_MANUAL,
            source_type=CalendarEvent.SOURCE_HABIT,
            source_id=str(habit.pk),
            is_protected=True,
            idempotency_key=compute_idempotency_key(
                habit.user_id, habit.name, start_dt, end_dt=end_dt,
                source_type='habit', source_id=str(habit.pk),
            ),
        )

    # Upsert recurrence rule
    freq_map = {
        'daily': RecurrenceRule.FREQ_DAILY,
        'weekly': RecurrenceRule.FREQ_WEEKLY,
        'monthly': RecurrenceRule.FREQ_MONTHLY,
    }
    frequency = freq_map.get(habit.frequency_type, RecurrenceRule.FREQ_DAILY)

    until_dt = None
    if habit.end_date:
        until_dt = timezone.make_aware(
            dt.datetime.combine(habit.end_date, dt.time(23, 59)),
            timezone.get_current_timezone(),
        )

    rule, created = RecurrenceRule.objects.update_or_create(
        event=event,
        defaults={
            'frequency': frequency,
            'interval': 1,
            'until_dt': until_dt,
            'byweekday': [],
        },
    )

    return event


def delete_habit_events(habit):
    """Remove all calendar events projected from a habit."""
    CalendarEvent.objects.filter(
        user=habit.user,
        source_type=CalendarEvent.SOURCE_HABIT,
        source_id=str(habit.pk),
    ).delete()
