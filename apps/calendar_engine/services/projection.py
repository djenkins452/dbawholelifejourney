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


def _cancel_stale_cos_prompts(user, calendar_event):
    """
    Cancel any pending CosPromptSchedule entries for a CalendarEvent
    whose times have changed. Prevents the assistant from referencing
    stale schedule data after a task/event is rescheduled.
    """
    try:
        from apps.cos.services.prompt_service import CosPromptService
        svc = CosPromptService(user)
        canceled = svc.cancel_prompts_for_event(calendar_event)
        if canceled:
            logger.debug(
                "Canceled %d stale CoS prompt(s) for rescheduled event %s",
                canceled, calendar_event.pk,
            )
    except ImportError:
        pass  # CoS module not installed
    except Exception as e:
        logger.debug("CoS prompt cancellation skipped: %s", e)


def _get_default_domain(slug='work'):
    """Get a LifeDomain by slug, or None if not found."""
    from apps.purpose.models import LifeDomain
    return LifeDomain.objects.filter(slug=slug, is_active=True).first()


def _resolve_domain_for_task(task):
    """
    Derive domain from task context.
    Tasks with scheduled times (routine or not) get domain based on title keywords.
    Regular tasks default to Work.
    """
    # Check title keywords for any task with a scheduled time or is_routine flag
    if getattr(task, 'is_routine', False) or getattr(task, 'scheduled_time', None):
        title_lower = task.title.lower()
        _TASK_DOMAIN_MAP = {
            'faith': [
                'quiet time', 'bible', 'prayer', 'devotional',
                'scripture', 'reading plan',
            ],
            'health': [
                'workout', 'exercise', 'run', 'gym', 'walk',
                'stretch', 'yoga', 'swim', 'cardio',
                'wake up', 'wake-up', 'morning routine',
            ],
        }
        for slug, keywords in _TASK_DOMAIN_MAP.items():
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
    Tasks with scheduled_time are routed to upsert_from_routine_task()
    to get time-specific execution blocks instead of 23:59 deadline markers.

    If the task has been soft-deleted, removes all its calendar events.
    """
    # Soft-deleted tasks should not have calendar events
    if getattr(task, 'status', 'active') == 'deleted':
        delete_task_events(task)
        return None

    # Any task with a scheduled_time gets a time-specific execution block
    if task.scheduled_time:
        # Clean up any stale deadline marker (may exist from before this fix)
        CalendarEvent.objects.filter(
            user=task.user,
            source_type=CalendarEvent.SOURCE_TASK,
            source_id=str(task.pk),
            event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
        ).delete()
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
        # Refresh from DB to get authoritative completion_status —
        # the in-memory instance may be stale after a partial save
        # (e.g., only scheduled_time was in update_fields).
        task.refresh_from_db(fields=['completion_status'])
        if task.is_completed:
            existing.status = CalendarEvent.STATUS_COMPLETED
        else:
            existing.status = CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(task.user, existing, old_start, start_dt)

        # Cancel stale CoS prompts when due date changes
        if old_start != start_dt:
            _cancel_stale_cos_prompts(task.user, existing)

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
        commitment_level=getattr(task, 'commitment_level', CalendarEvent.COMMITMENT_IMPORTANT),
        status=CalendarEvent.STATUS_COMPLETED if task.is_completed else CalendarEvent.STATUS_SCHEDULED,
        idempotency_key=compute_idempotency_key(
            task.user_id, task_title, start_dt, end_dt=end_dt,
            source_type='task', source_id=str(task.pk),
        ),
    )


def upsert_from_routine_task(task):
    """
    Create/update a time-specific EXECUTION_BLOCK for a task with scheduled_time.

    Unlike deadline markers at 23:59, this creates actual time blocks at the
    task's scheduled_time with proper duration — so the event appears at the
    right time on the calendar.

    Works for ANY task with scheduled_time, not just is_routine tasks.

    Args:
        task: Task instance with scheduled_time and due_date set

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
    # Refresh from DB to get authoritative completion_status —
    # the in-memory instance may be stale after a partial save.
    task.refresh_from_db(fields=['completion_status'])
    status = (
        CalendarEvent.STATUS_COMPLETED if task.is_completed
        else CalendarEvent.STATUS_SCHEDULED
    )

    commitment = getattr(task, 'commitment_level', CalendarEvent.COMMITMENT_IMPORTANT)

    if existing:
        old_start = existing.start_dt
        existing.title = task.title
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.is_all_day = False
        existing.status = status
        existing.commitment_level = commitment
        existing.save()
        _log_schedule_change(task.user, existing, old_start, start_dt)

        # If times changed, cancel stale CosPromptSchedule entries so
        # the assistant doesn't reference the old schedule.
        if old_start != start_dt:
            _cancel_stale_cos_prompts(task.user, existing)

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
        commitment_level=commitment,
        status=status,
        idempotency_key=compute_idempotency_key(
            task.user_id, task.title, start_dt, end_dt=end_dt,
            source_type='task', source_id=str(task.pk),
        ),
    )


def upsert_execution_block_for_task(task, start_dt, end_dt):
    """
    Create or update an EXECUTION_BLOCK linked to a task.
    Checks for existing execution blocks for this task to prevent duplicates.
    Does not overwrite deadline markers.
    """
    # Check for ANY existing execution block for this task (same source)
    existing = CalendarEvent.objects.filter(
        user=task.user,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
        status=CalendarEvent.STATUS_SCHEDULED,
        deleted_at__isnull=True,
    ).first()

    domain = _resolve_domain_for_task(task)

    if existing:
        old_start = existing.start_dt
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.save(update_fields=['start_dt', 'end_dt', 'domain', 'updated_at'])
        _log_schedule_change(task.user, existing, old_start, start_dt)
        return existing

    # Clean up stale deadline marker — execution block replaces it.
    # Source-backed idempotency keys are hash(user, source_type, source_id)
    # so a deadline marker and execution block for the same task share the
    # same key and would violate the unique constraint.
    CalendarEvent.objects.filter(
        user=task.user,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        event_kind=CalendarEvent.KIND_DEADLINE_MARKER,
    ).delete()

    return CalendarEvent.objects.create(
        user=task.user,
        title=task.title,
        start_dt=start_dt,
        end_dt=end_dt,
        domain=domain,
        event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
        source_type=CalendarEvent.SOURCE_TASK,
        source_id=str(task.pk),
        idempotency_key=compute_idempotency_key(
            task.user_id, task.title, start_dt, end_dt=end_dt,
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

    habit_commitment = getattr(habit, 'commitment_level', CalendarEvent.COMMITMENT_IMPORTANT)

    if existing:
        old_start = existing.start_dt
        existing.title = habit.name
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.is_protected = True
        existing.commitment_level = habit_commitment
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
            commitment_level=habit_commitment,
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


# ──────────────────────────────────────────────────────────
# Medicine Schedule Projections (Architecture Evolution Phase 1)
# ──────────────────────────────────────────────────────────

def upsert_from_medicine_schedule(schedule):
    """
    Create/update an EXECUTION_BLOCK for a MedicineSchedule.

    Each MedicineSchedule instance represents a single daily dose time
    (e.g., "Metformin at 8:00 AM"). This projects it as a recurring
    CalendarEvent with commitment_level='non_negotiable'.

    Contract: CalendarEvent = scheduled commitment INSTANCE, not definition.
    The MedicineSchedule is the definition; the CalendarEvent is the daily instance.
    For recurring schedules, we use RecurrenceRule to generate occurrences dynamically.
    """
    if not schedule.is_active:
        delete_medicine_events(schedule)
        return None

    medicine = schedule.medicine
    user = medicine.user

    existing = CalendarEvent.objects.filter(
        user=user,
        source_type=CalendarEvent.SOURCE_MEDICINE_SCHEDULE,
        source_id=str(schedule.pk),
    ).first()

    # Build title: "Take Metformin 500mg" or "Take Metformin"
    dosage_str = f" {medicine.dosage}" if medicine.dosage else ""
    title = f"Take {medicine.name}{dosage_str}"

    # Anchor event at schedule's time on medicine start_date or today
    from apps.core.utils import get_user_today
    anchor_date = getattr(medicine, 'start_date', None) or get_user_today(user)

    from zoneinfo import ZoneInfo
    user_tz = ZoneInfo(user.preferences.timezone_iana)
    start_dt = timezone.make_aware(
        dt.datetime.combine(anchor_date, schedule.scheduled_time),
        user_tz,
    )
    end_dt = start_dt + dt.timedelta(minutes=5)  # Medication takes ~5 min

    domain = _get_default_domain('health')

    if existing:
        old_start = existing.start_dt
        existing.title = title
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.commitment_level = CalendarEvent.COMMITMENT_NON_NEGOTIABLE
        existing.status = CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(user, existing, old_start, start_dt)
        event = existing
    else:
        event = CalendarEvent.objects.create(
            user=user,
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            is_all_day=False,
            domain=domain,
            event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
            source_type=CalendarEvent.SOURCE_MEDICINE_SCHEDULE,
            source_id=str(schedule.pk),
            commitment_level=CalendarEvent.COMMITMENT_NON_NEGOTIABLE,
            idempotency_key=compute_idempotency_key(
                user.pk, title, start_dt, end_dt=end_dt,
                source_type='medicine_schedule', source_id=str(schedule.pk),
            ),
        )

    # Upsert recurrence rule — medicine doses repeat on configured days
    days_list = schedule.days_list
    # Convert Python weekday (0=Mon) to ISO weekday (1=Mon) for RecurrenceRule
    iso_days = [d + 1 for d in days_list] if days_list else []

    RecurrenceRule.objects.update_or_create(
        event=event,
        defaults={
            'frequency': RecurrenceRule.FREQ_DAILY,
            'interval': 1,
            'byweekday': iso_days if iso_days and len(iso_days) < 7 else [],
            'timezone': user.preferences.timezone_iana,
        },
    )

    return event


def delete_medicine_events(schedule):
    """Remove all calendar events projected from a medicine schedule."""
    user = schedule.intake.user
    CalendarEvent.objects.filter(
        user=user,
        source_type=CalendarEvent.SOURCE_MEDICINE_SCHEDULE,
        source_id=str(schedule.pk),
    ).delete()


# ──────────────────────────────────────────────────────────
# Faith Routine Projections (Architecture Evolution Phase 1)
# ──────────────────────────────────────────────────────────

def upsert_from_faith_routine(user_plan):
    """
    Create/update a recurring CalendarEvent for a UserReadingPlan.

    Projects the reading plan as a daily commitment at the plan's
    reminder_time (or default 6:30 AM).

    Contract: CalendarEvent = scheduled commitment INSTANCE.
    The UserReadingPlan + ReadingPlanDay are the definitions.
    """
    if user_plan.plan_status not in ('active',):
        delete_faith_events(user_plan)
        return None

    user = user_plan.user
    template = user_plan.template

    existing = CalendarEvent.objects.filter(
        user=user,
        source_type=CalendarEvent.SOURCE_FAITH_ROUTINE,
        source_id=str(user_plan.pk),
    ).first()

    title = f"Bible Reading: {template.name}"
    reminder_time = user_plan.reminder_time or dt.time(6, 30)

    from zoneinfo import ZoneInfo
    user_tz = ZoneInfo(user.preferences.timezone_iana)
    start_dt = timezone.make_aware(
        dt.datetime.combine(user_plan.started_at.date(), reminder_time),
        user_tz,
    )
    end_dt = start_dt + dt.timedelta(minutes=20)  # ~20 min for reading

    domain = _get_default_domain('faith')

    if existing:
        old_start = existing.start_dt
        existing.title = title
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.commitment_level = CalendarEvent.COMMITMENT_IMPORTANT
        existing.status = CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(user, existing, old_start, start_dt)
        event = existing
    else:
        event = CalendarEvent.objects.create(
            user=user,
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            is_all_day=False,
            domain=domain,
            event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
            source_type=CalendarEvent.SOURCE_FAITH_ROUTINE,
            source_id=str(user_plan.pk),
            commitment_level=CalendarEvent.COMMITMENT_IMPORTANT,
            idempotency_key=compute_idempotency_key(
                user.pk, title, start_dt, end_dt=end_dt,
                source_type='faith_routine', source_id=str(user_plan.pk),
            ),
        )

    # Upsert recurrence — daily until plan ends
    RecurrenceRule.objects.update_or_create(
        event=event,
        defaults={
            'frequency': RecurrenceRule.FREQ_DAILY,
            'interval': 1,
            'byweekday': [],
            'timezone': user.preferences.timezone_iana,
        },
    )

    return event


def delete_faith_events(user_plan):
    """Remove all calendar events projected from a faith routine."""
    CalendarEvent.objects.filter(
        user=user_plan.user,
        source_type=CalendarEvent.SOURCE_FAITH_ROUTINE,
        source_id=str(user_plan.pk),
    ).delete()


# ──────────────────────────────────────────────────────────
# Workout Schedule Projections (Architecture Evolution Phase 1)
# ──────────────────────────────────────────────────────────

def upsert_from_workout_schedule(schedule):
    """
    Create/update a recurring CalendarEvent for a WorkoutSchedule entry.

    Each WorkoutSchedule maps a day-of-week to a template within a plan.
    Projects as a weekly recurring event on the configured day.

    Contract: CalendarEvent = scheduled commitment INSTANCE.
    The WorkoutSchedule is the definition.
    """
    if schedule.is_rest_day:
        delete_workout_events(schedule)
        return None

    plan = schedule.plan
    if not plan.is_active:
        delete_workout_events(schedule)
        return None

    user = plan.user

    existing = CalendarEvent.objects.filter(
        user=user,
        source_type=CalendarEvent.SOURCE_WORKOUT_SCHEDULE,
        source_id=str(schedule.pk),
    ).first()

    title = f"Workout: {schedule.template.name}"
    preferred_time = schedule.preferred_time or dt.time(17, 0)  # Default 5 PM

    # Find the next occurrence of this day of week
    from apps.core.utils import get_user_today
    today = get_user_today(user)
    # schedule.day_of_week: 0=Mon → isoweekday 1=Mon
    target_iso = schedule.day_of_week + 1
    days_ahead = (target_iso - today.isoweekday()) % 7
    anchor_date = today + dt.timedelta(days=days_ahead)

    from zoneinfo import ZoneInfo
    user_tz = ZoneInfo(user.preferences.timezone_iana)
    start_dt = timezone.make_aware(
        dt.datetime.combine(anchor_date, preferred_time),
        user_tz,
    )
    end_dt = start_dt + dt.timedelta(minutes=60)  # ~60 min workout

    domain = _get_default_domain('health')

    if existing:
        old_start = existing.start_dt
        existing.title = title
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.domain = domain
        existing.commitment_level = CalendarEvent.COMMITMENT_IMPORTANT
        existing.status = CalendarEvent.STATUS_SCHEDULED
        existing.save()
        _log_schedule_change(user, existing, old_start, start_dt)
        event = existing
    else:
        event = CalendarEvent.objects.create(
            user=user,
            title=title,
            start_dt=start_dt,
            end_dt=end_dt,
            is_all_day=False,
            domain=domain,
            event_kind=CalendarEvent.KIND_EXECUTION_BLOCK,
            source_type=CalendarEvent.SOURCE_WORKOUT_SCHEDULE,
            source_id=str(schedule.pk),
            commitment_level=CalendarEvent.COMMITMENT_IMPORTANT,
            idempotency_key=compute_idempotency_key(
                user.pk, title, start_dt, end_dt=end_dt,
                source_type='workout_schedule', source_id=str(schedule.pk),
            ),
        )

    # Upsert recurrence — weekly on the configured day
    RecurrenceRule.objects.update_or_create(
        event=event,
        defaults={
            'frequency': RecurrenceRule.FREQ_WEEKLY,
            'interval': 1,
            'byweekday': [target_iso],
            'timezone': user.preferences.timezone_iana,
        },
    )

    return event


def delete_workout_events(schedule):
    """Remove all calendar events projected from a workout schedule."""
    user = schedule.plan.user
    CalendarEvent.objects.filter(
        user=user,
        source_type=CalendarEvent.SOURCE_WORKOUT_SCHEDULE,
        source_id=str(schedule.pk),
    ).delete()


# ──────────────────────────────────────────────────────────
# Life Event Projection
# ──────────────────────────────────────────────────────────

_LIFE_EVENT_DOMAIN_MAP = {
    'personal': 'personal',
    'family': 'family',
    'household': 'personal',
    'faith': 'faith',
    'health': 'health',
    'work': 'work',
    'social': 'relationships',
    'travel': 'personal',
    'other': 'personal',
}


def upsert_from_life_event(event):
    """
    Create/update a CalendarEvent from a LifeEvent.
    Handles all-day events, timed events, and recurring events.
    """
    user_tz = timezone.get_current_timezone()

    # Build start/end datetimes
    if event.is_all_day or not event.start_time:
        start_dt = timezone.make_aware(
            dt.datetime.combine(event.start_date, dt.time(0, 0)), user_tz
        )
        end_date = event.end_date or event.start_date
        end_dt = timezone.make_aware(
            dt.datetime.combine(end_date, dt.time(23, 59)), user_tz
        )
        is_all_day = True
    else:
        start_dt = timezone.make_aware(
            dt.datetime.combine(event.start_date, event.start_time), user_tz
        )
        if event.end_date and event.end_time:
            end_dt = timezone.make_aware(
                dt.datetime.combine(event.end_date, event.end_time), user_tz
            )
        elif event.end_time:
            end_dt = timezone.make_aware(
                dt.datetime.combine(event.start_date, event.end_time), user_tz
            )
        else:
            end_dt = start_dt + dt.timedelta(hours=1)
        is_all_day = False

    # Resolve domain
    slug = _LIFE_EVENT_DOMAIN_MAP.get(event.event_type, 'personal')
    domain = _get_default_domain(slug)

    existing = CalendarEvent.objects.filter(
        user=event.user,
        source_type=CalendarEvent.SOURCE_LIFE_EVENT,
        source_id=str(event.pk),
    ).first()

    if existing:
        old_start = existing.start_dt
        existing.title = event.title
        existing.description = event.description or ''
        existing.start_dt = start_dt
        existing.end_dt = end_dt
        existing.is_all_day = is_all_day
        existing.domain = domain
        existing.save()
        _log_schedule_change(event.user, existing, old_start, start_dt)
        return existing

    cal_event = CalendarEvent.objects.create(
        user=event.user,
        title=event.title,
        description=event.description or '',
        start_dt=start_dt,
        end_dt=end_dt,
        is_all_day=is_all_day,
        domain=domain,
        event_kind=CalendarEvent.KIND_MANUAL,
        source_type=CalendarEvent.SOURCE_LIFE_EVENT,
        source_id=str(event.pk),
        idempotency_key=compute_idempotency_key(
            event.user_id, event.title, start_dt, end_dt=end_dt,
            source_type='life_event', source_id=str(event.pk),
        ),
    )
    return cal_event
