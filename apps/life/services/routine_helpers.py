"""
Routine domain — PUBLIC service interface.

This is the ONLY module that views and external code should import for
routine operations. It exposes:
  - toggle_routine_completion()  — toggle a schedule item's completion
  - skip_routine()               — mark a schedule item as skipped
  - toggle_routine_complete()    — toggle ALL items in a routine (routine-level checkbox)
  - reschedule_routine_item()    — reschedule a missed item to later same day
  - get_routine_completion_state() — derive routine completion from item logs

For reading routine state (items, windows, summaries), use:
  apps.core.ai_state.state_builder.build_routine_state()

Internal computation lives in _routine_internal.py — do NOT import
that module from views or other services.

Status transition rules (strict execution model):
  - One RoutineLog per schedule per day (enforced by unique_together)
  - none → completed  (toggle: first check)
  - completed → none  (toggle: un-check, deletes log)
  - skipped → completed  (toggle: re-check a skipped item)
  - rescheduled → completed_late  (toggle: complete a rescheduled item)
  - none → skipped  (explicit skip action)
  - none → rescheduled  (reschedule a missed item to later same day)
  - Missed is COMPUTED, not stored (absence of log + time past grace)
  - Rescheduled items remain actionable until day close (never auto-missed)
  - No auto-complete — completion is explicit only

Routine-level completion is DERIVED from item logs, never stored:
  - routine_complete = all(applicable items have completed logs for today)
"""

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def toggle_routine_completion(user, schedule, target_date, completion_mode=None):
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
        completion_mode: optional str — 'scheduled' (on time), 'late' (now),
            or None (auto-detect from time). Controls whether user asserts
            completion happened at scheduled time.

    Returns:
        dict: {status: str, is_completed: bool, completed_as_scheduled: bool}
    """
    from apps.life.models import RoutineLog

    existing_log = RoutineLog.objects.filter(
        schedule=schedule, scheduled_date=target_date,
    ).first()

    if existing_log:
        if existing_log.log_status in ('completed', 'completed_late'):
            existing_log.delete()
            return {'status': 'pending', 'is_completed': False,
                    'completed_as_scheduled': False}
        elif existing_log.log_status == 'skipped':
            as_scheduled = (completion_mode == 'scheduled')
            existing_log.log_status = 'completed' if as_scheduled else 'completed'
            existing_log.completed_at = timezone.now()
            existing_log.completed_as_scheduled = as_scheduled
            existing_log.save(update_fields=[
                'log_status', 'completed_at', 'completed_as_scheduled', 'updated_at',
            ])
            return {'status': 'completed', 'is_completed': True,
                    'completed_as_scheduled': as_scheduled}
        elif existing_log.log_status == 'rescheduled':
            # Completing a rescheduled item — user can assert on-time
            as_scheduled = (completion_mode == 'scheduled')
            existing_log.log_status = 'completed' if as_scheduled else 'completed_late'
            existing_log.completed_at = timezone.now()
            existing_log.completed_as_scheduled = as_scheduled
            existing_log.save(update_fields=[
                'log_status', 'completed_at', 'completed_as_scheduled', 'updated_at',
            ])
            return {
                'status': existing_log.log_status, 'is_completed': True,
                'completed_as_scheduled': as_scheduled,
            }
        else:
            return {'status': existing_log.log_status, 'is_completed': False,
                    'completed_as_scheduled': False}
    else:
        from apps.core.utils import classify_time_status, get_user_now, get_user_today

        # Determine completion mode
        if completion_mode == 'scheduled':
            # User asserts they completed at scheduled time
            log_status = 'completed'
            as_scheduled = True
        elif completion_mode == 'late':
            # User explicitly says they're completing late
            log_status = 'completed_late'
            as_scheduled = False
        else:
            # Auto-detect from time (existing behavior)
            log_status = 'completed'
            as_scheduled = True
            user_now = get_user_now(user)
            user_today = get_user_today(user)
            if target_date == user_today and schedule.scheduled_time:
                result = classify_time_status(
                    user_today, schedule.scheduled_time, user_now,
                    grace_minutes=getattr(schedule, 'grace_period_minutes', 0) or 0,
                )
                if result['status'] == 'overdue':
                    log_status = 'completed_late'
                    as_scheduled = False

        RoutineLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=target_date,
            log_status=log_status,
            completed_at=timezone.now(),
            completed_as_scheduled=as_scheduled,
        )
        return {'status': log_status, 'is_completed': True,
                'completed_as_scheduled': as_scheduled}


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


def _get_applicable_items(routine, target_date):
    """Get active routine items that apply to a specific date."""
    weekday = target_date.weekday()
    items = []
    for item in routine.items.filter(is_active=True):
        if item.specific_date:
            if item.specific_date == target_date:
                items.append(item)
        elif item.applies_to_day(weekday):
            items.append(item)
    return items


def get_routine_completion_state(user, routine, target_date):
    """
    Derive routine completion from item execution records.

    Routine completion is NEVER stored — it is always computed from
    the individual RoutineLog records for today's applicable items.

    Args:
        user: User instance
        routine: Routine instance (must belong to user)
        target_date: date

    Returns:
        dict: {all_complete: bool, completed_count: int, total_count: int}
    """
    from apps.life.models import RoutineLog

    applicable = _get_applicable_items(routine, target_date)
    total = len(applicable)

    if total == 0:
        return {'all_complete': False, 'completed_count': 0, 'total_count': 0}

    schedule_ids = [item.id for item in applicable]
    completed_ids = set(
        RoutineLog.objects.filter(
            schedule_id__in=schedule_ids,
            scheduled_date=target_date,
            log_status__in=('completed', 'completed_late'),
        ).values_list('schedule_id', flat=True)
    )

    completed_count = len(completed_ids)
    return {
        'all_complete': completed_count == total,
        'completed_count': completed_count,
        'total_count': total,
    }


@transaction.atomic
def toggle_routine_complete(user, routine, target_date):
    """
    Toggle ALL items in a routine for a date (routine-level checkbox).

    Derives current state from item logs, then:
      - If NOT all complete → create completed logs for all pending items
      - If all complete → delete today's completed logs (revert to pending)

    This is the bidirectional sync: checking the routine checkbox
    propagates to all child items. Unchecking reverts them all.

    Args:
        user: User instance
        routine: Routine instance (must belong to user)
        target_date: date

    Returns:
        dict: {all_complete: bool, completed_count: int, total_count: int}
    """
    from apps.life.models import RoutineLog

    applicable = _get_applicable_items(routine, target_date)
    total = len(applicable)

    if total == 0:
        return {'all_complete': False, 'completed_count': 0, 'total_count': 0}

    schedule_ids = [item.id for item in applicable]
    existing_logs = {
        log.schedule_id: log
        for log in RoutineLog.objects.filter(
            schedule_id__in=schedule_ids,
            scheduled_date=target_date,
        )
    }

    completed_ids = {
        sid for sid, log in existing_logs.items()
        if log.log_status in ('completed', 'completed_late')
    }
    currently_all_complete = len(completed_ids) == total

    now = timezone.now()

    if currently_all_complete:
        # Uncheck: delete today's completed/completed_late logs → items become pending
        RoutineLog.objects.filter(
            schedule_id__in=schedule_ids,
            scheduled_date=target_date,
            log_status__in=('completed', 'completed_late'),
        ).delete()
        return {'all_complete': False, 'completed_count': 0, 'total_count': total}
    else:
        # Check: create completed logs for all items that aren't already completed
        for item in applicable:
            if item.id in completed_ids:
                continue  # already completed, leave it
            existing = existing_logs.get(item.id)
            if existing:
                # Has a log (skipped, rescheduled, or other) — update to completed
                # Rescheduled items become completed_late (past original window)
                if existing.log_status == 'rescheduled':
                    existing.log_status = 'completed_late'
                else:
                    existing.log_status = 'completed'
                existing.completed_at = now
                existing.save(update_fields=['log_status', 'completed_at', 'updated_at'])
            else:
                # No log — create completed (or completed_late if past window)
                from apps.core.utils import classify_time_status, get_user_now, get_user_today
                batch_status = 'completed'
                user_now = get_user_now(user)
                user_today = get_user_today(user)
                if target_date == user_today and item.scheduled_time:
                    ts = classify_time_status(
                        user_today, item.scheduled_time, user_now,
                        grace_minutes=getattr(item, 'grace_period_minutes', 0) or 0,
                    )
                    if ts['status'] == 'overdue':
                        batch_status = 'completed_late'
                RoutineLog.objects.create(
                    user=user,
                    schedule=item,
                    scheduled_date=target_date,
                    log_status=batch_status,
                    completed_at=now,
                )
        return {'all_complete': True, 'completed_count': total, 'total_count': total}


def close_unresolved_rescheduled_logs():
    """
    Day-close cleanup: convert all past-day rescheduled logs to skipped.

    Called by the nightly process_recurring_tasks Celery task.
    Rescheduled items that were never completed or skipped by day close
    are finalized as 'skipped' (behavior scoring already counts them as
    missed via the unresolved-rescheduled penalty in domain_routine.py).

    This prevents stale 'rescheduled' logs from persisting indefinitely.
    """
    from datetime import date

    from apps.life.models import RoutineLog

    today = date.today()  # Server time — close all days before today
    stale_count = RoutineLog.objects.filter(
        log_status='rescheduled',
        scheduled_date__lt=today,
    ).update(
        log_status='skipped',
        notes='Auto-closed: rescheduled but not completed by end of day',
    )
    if stale_count:
        logger.info(
            "Day-close: converted %d unresolved rescheduled logs to skipped",
            stale_count,
        )
    return stale_count


def reschedule_routine_item(user, schedule, target_date, new_time):
    """
    Reschedule a missed routine item to a later time on the same day.

    Creates or updates a RoutineLog with status='rescheduled' and
    rescheduled_time set. This is a log-level override — the RoutineSchedule
    template is NEVER modified.

    Transition rules:
        no log (missed) → rescheduled
        rescheduled → rescheduled (update time)
        skipped → rescheduled (user changed mind)
        completed/completed_late → error (already done)

    Validation:
        - target_date must be today in user local time
        - new_time must be after user's current local time
        - new_time must be before day close (23:59)

    Args:
        user: User instance
        schedule: RoutineSchedule instance (must belong to user)
        target_date: date
        new_time: datetime.time — the new time to reschedule to

    Returns:
        dict: {success: bool, status: str, rescheduled_time: str, item_name: str}
              or {success: False, error: str} on validation failure
    """
    from datetime import time as _time_cls

    from apps.core.utils import get_user_now, get_user_today
    from apps.life.models import RoutineLog

    # Validation 1: target_date must be today
    user_today = get_user_today(user)
    if target_date != user_today:
        return {'success': False, 'error': 'Can only reschedule items for today'}

    # Validation 2: new_time must be after current user time
    user_now = get_user_now(user)
    if new_time <= user_now.time():
        return {
            'success': False,
            'error': f'New time must be later than current time ({user_now.strftime("%I:%M %p")})',
        }

    # Validation 3: new_time must be before day close
    if new_time >= _time_cls(23, 59):
        return {'success': False, 'error': 'New time must be before 11:59 PM'}

    # Check existing log
    existing_log = RoutineLog.objects.filter(
        schedule=schedule, scheduled_date=target_date,
    ).first()

    if existing_log and existing_log.log_status in ('completed', 'completed_late'):
        return {'success': False, 'error': 'Item is already completed'}

    if existing_log:
        # Update existing log (skipped/rescheduled → rescheduled with new time)
        # Multiple reschedules allowed — as long as it gets done
        existing_log.log_status = 'rescheduled'
        existing_log.rescheduled_time = new_time
        existing_log.completed_at = None
        existing_log.reschedule_count = (existing_log.reschedule_count or 0) + 1
        existing_log.save(update_fields=[
            'log_status', 'rescheduled_time', 'completed_at',
            'reschedule_count', 'updated_at',
        ])
        count = existing_log.reschedule_count
    else:
        # Create new rescheduled log
        RoutineLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=target_date,
            log_status='rescheduled',
            rescheduled_time=new_time,
            completed_at=None,
            reschedule_count=1,
        )
        count = 1

    formatted_time = new_time.strftime('%I:%M %p').lstrip('0')
    return {
        'success': True,
        'status': 'rescheduled',
        'rescheduled_time': formatted_time,
        'reschedule_count': count,
        'item_name': schedule.name,
    }
