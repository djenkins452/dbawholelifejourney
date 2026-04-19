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
from datetime import datetime as _dt_cls, timedelta as _td

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _compute_timing_and_performed_at(user, schedule, user_today, user_now):
    """Compute performed_at and timing classification for a completion action.

    Uses the user's timezone and the schedule's grace_period_minutes to
    determine whether the completion is on_time, late, or early.

    Args:
        user: User instance (for timezone)
        schedule: RoutineSchedule instance (has scheduled_time, grace_period_minutes)
        user_today: date in user's timezone
        user_now: datetime in user's timezone (timezone-aware)

    Returns:
        tuple: (performed_at: datetime, timing: str)
    """
    from apps.core.utils import _get_user_tz

    if not schedule.scheduled_time:
        # No scheduled time → default to now/on_time
        return user_now, "on_time"

    user_tz = _get_user_tz(user)
    sched_dt = timezone.make_aware(
        _dt_cls.combine(user_today, schedule.scheduled_time), user_tz,
    )
    grace = getattr(schedule, 'grace_period_minutes', 0) or 0
    window_start = sched_dt - _td(minutes=grace)
    window_end = sched_dt + _td(minutes=grace)

    if window_start <= user_now <= window_end:
        return sched_dt, "on_time"
    elif user_now > window_end:
        return user_now, "late"
    else:
        return user_now, "early"


def _compute_timing_for_time(user, schedule, user_today, effective_time):
    """Compute timing classification for a specific effective_time.

    Used by auto-complete to classify an activity's actual timestamp
    against the schedule's grace window.

    Args:
        user: User instance (for timezone)
        schedule: RoutineSchedule instance
        user_today: date in user's timezone
        effective_time: datetime (aware) — when the activity actually happened

    Returns:
        tuple: (performed_at: datetime, timing: str)
    """
    from apps.core.utils import _get_user_tz

    if not schedule.scheduled_time:
        return effective_time, "on_time"

    user_tz = _get_user_tz(user)
    sched_dt = timezone.make_aware(
        _dt_cls.combine(user_today, schedule.scheduled_time), user_tz,
    )
    grace = getattr(schedule, 'grace_period_minutes', 0) or 0
    window_start = sched_dt - _td(minutes=grace)
    window_end = sched_dt + _td(minutes=grace)

    if window_start <= effective_time <= window_end:
        return effective_time, "on_time"
    elif effective_time > window_end:
        return effective_time, "late"
    else:
        return effective_time, "early"


def _get_scheduled_datetime(user, schedule, user_today):
    """Build a timezone-aware datetime from schedule.scheduled_time + date."""
    from apps.core.utils import _get_user_tz

    if not schedule.scheduled_time:
        return None
    user_tz = _get_user_tz(user)
    return timezone.make_aware(
        _dt_cls.combine(user_today, schedule.scheduled_time), user_tz,
    )


def toggle_routine_completion(user, schedule, target_date, completion_mode=None):
    """
    Toggle a routine schedule item's completion for a date.

    Transition rules:
        no log → completed (create)
        completed/completed_late → pending (delete log)
        skipped → completed (update)

    Activity-type routines (e.g., "Workout" bridged from WorkoutSession) are
    normally auto-completed by their data source. Manual toggling is STILL
    permitted — the user must always retain control, because auto-complete
    can fail silently (bridge broken, integration down, data not yet synced)
    and the user needs an escape hatch to correct the dashboard. Manual
    overrides are distinguished from auto-completions via the RoutineLog's
    `completion_source` field (SOURCE_MANUAL vs. SOURCE_WORKOUT etc.).

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

    from apps.core.utils import get_user_now, get_user_today
    user_now = get_user_now(user)
    user_today = get_user_today(user)
    now = timezone.now()

    # ── Compute performed_at, timing, completion_source based on mode ──
    if completion_mode == 'scheduled':
        # "Done at Scheduled Time" — user asserts on-time
        sched_dt = _get_scheduled_datetime(user, schedule, target_date)
        performed_at = sched_dt or now
        timing = RoutineLog.TIMING_ON_TIME
        log_status = 'completed'
        as_scheduled = True
        source = RoutineLog.SOURCE_SCHEDULED_OVERRIDE
    elif completion_mode == 'late':
        # User explicitly says completing late
        performed_at = now
        timing = RoutineLog.TIMING_LATE
        log_status = 'completed_late'
        as_scheduled = False
        source = RoutineLog.SOURCE_MANUAL
    else:
        # Auto-detect from grace window
        if target_date == user_today and schedule.scheduled_time:
            performed_at, timing = _compute_timing_and_performed_at(
                user, schedule, user_today, user_now,
            )
            if timing == 'late':
                log_status = 'completed_late'
                as_scheduled = False
            else:
                log_status = 'completed'
                as_scheduled = True
        else:
            performed_at = now
            timing = RoutineLog.TIMING_ON_TIME
            log_status = 'completed'
            as_scheduled = True
        source = RoutineLog.SOURCE_MANUAL

    if existing_log:
        if existing_log.log_status in ('completed', 'completed_late'):
            if completion_mode == 'scheduled':
                # Re-click override: overwrite to on_time
                existing_log.log_status = log_status
                existing_log.completed_at = now
                existing_log.completed_as_scheduled = as_scheduled
                existing_log.performed_at = performed_at
                existing_log.timing = timing
                existing_log.completion_source = source
                existing_log.save(update_fields=[
                    'log_status', 'completed_at', 'completed_as_scheduled',
                    'performed_at', 'timing', 'completion_source', 'updated_at',
                ])
                return {'status': log_status, 'is_completed': True,
                        'completed_as_scheduled': as_scheduled, 'timing': timing}
            else:
                # Un-check: delete log → pending
                existing_log.delete()
                return {'status': 'pending', 'is_completed': False,
                        'completed_as_scheduled': False, 'timing': ''}
        elif existing_log.log_status == 'skipped':
            existing_log.log_status = log_status
            existing_log.completed_at = now
            existing_log.completed_as_scheduled = as_scheduled
            existing_log.performed_at = performed_at
            existing_log.timing = timing
            existing_log.completion_source = source
            existing_log.save(update_fields=[
                'log_status', 'completed_at', 'completed_as_scheduled',
                'performed_at', 'timing', 'completion_source', 'updated_at',
            ])
            return {'status': log_status, 'is_completed': True,
                    'completed_as_scheduled': as_scheduled, 'timing': timing}
        elif existing_log.log_status == 'rescheduled':
            existing_log.log_status = log_status
            existing_log.completed_at = now
            existing_log.completed_as_scheduled = as_scheduled
            existing_log.performed_at = performed_at
            existing_log.timing = timing
            existing_log.completion_source = source
            existing_log.save(update_fields=[
                'log_status', 'completed_at', 'completed_as_scheduled',
                'performed_at', 'timing', 'completion_source', 'updated_at',
            ])
            return {
                'status': existing_log.log_status, 'is_completed': True,
                'completed_as_scheduled': as_scheduled, 'timing': timing,
            }
        else:
            return {'status': existing_log.log_status, 'is_completed': False,
                    'completed_as_scheduled': False, 'timing': ''}
    else:
        RoutineLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=target_date,
            log_status=log_status,
            completed_at=now,
            completed_as_scheduled=as_scheduled,
            performed_at=performed_at,
            timing=timing,
            completion_source=source,
            routine_at_time=schedule.routine,
        )
        return {'status': log_status, 'is_completed': True,
                'completed_as_scheduled': as_scheduled, 'timing': timing}


def auto_complete_routine_schedules(user, keyword, source, completion_time=None,
                                    source_object_id=None, target_date=None):
    """
    Auto-complete matching RoutineSchedule items for a specific date.

    Called from cross-module signals (workout, medicine, bible reading)
    to mark matching routine items as completed.  First-workout-wins:
    once a routine is auto-completed for the day, later calls are no-ops.

    Matching priority:
      1. activity_type field (structured, preferred)
      2. name__icontains keyword (TEMPORARY FALLBACK — remove once all
         activity routines are backfilled with activity_type)

    Args:
        user: User instance
        keyword: Case-insensitive keyword to match against schedule name
                 (e.g., "workout"). Used only as fallback.
        source: str — completion_source value ('workout', 'medicine', etc.)
        completion_time: datetime (aware) used for timeliness classification.
                        Prefer workout start time over end time.
                        Defaults to now if None.
        source_object_id: int — PK of the source object (e.g., WorkoutSession.pk)
                         for traceability.
        target_date: date — the date to auto-complete for. Defaults to today
                    in user's timezone. Callers should pass the activity's
                    actual date to prevent cross-day mismatch bugs.

    Returns:
        list of dicts: [{schedule_id, status, created}] for each matched item
    """
    from django.db import models as _m

    from apps.core.utils import get_user_now, get_user_today
    from apps.life.models import RoutineLog, RoutineSchedule

    user_today = target_date or get_user_today(user)
    user_now = get_user_now(user)
    weekday = user_today.weekday()

    # ── Find matching schedules ──
    # Prefer structured activity_type; fall back to name matching (temporary).
    matching = RoutineSchedule.objects.filter(
        routine__user=user,
        is_active=True,
    ).filter(
        _m.Q(activity_type=source)
        | _m.Q(name__icontains=keyword)  # TEMPORARY FALLBACK — remove when backfill complete
    ).select_related('routine')

    results = []
    effective_time = completion_time or user_now

    for schedule in matching:
        # Day-of-week check
        if schedule.specific_date:
            if schedule.specific_date != user_today:
                continue
        elif not schedule.applies_to_day(weekday):
            continue

        # ── First-workout-wins / idempotency ──
        # If a log already exists for today (manual or auto), skip.
        if RoutineLog.objects.filter(
            schedule=schedule, scheduled_date=user_today,
        ).exists():
            continue

        # Log when using name-based fallback (not activity_type)
        if not schedule.activity_type:
            logger.info(
                "ROUTINE_AUTOCOMPLETE_FALLBACK schedule=%s matched via name '%s' "
                "(no activity_type set — temporary fallback)",
                schedule.pk, schedule.name,
            )

        # ── Timeliness classification ──
        # Compute timing from activity's actual timestamp vs schedule grace.
        performed_at, timing = _compute_timing_for_time(
            user, schedule, user_today, effective_time,
        )
        if timing == 'late':
            log_status = 'completed_late'
            as_scheduled = False
        else:
            log_status = 'completed'
            as_scheduled = True

        RoutineLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=user_today,
            log_status=log_status,
            completed_at=timezone.now(),
            completed_as_scheduled=as_scheduled,
            performed_at=performed_at,
            timing=timing,
            completion_source=source,
            source_object_id=source_object_id,
            routine_at_time=schedule.routine,
        )
        results.append({
            'schedule_id': schedule.pk,
            'status': log_status,
            'created': True,
        })

    return results


def get_fallback_usage_metrics():
    """
    Report on name-based fallback vs structured activity_type matching.

    Returns dict with counts of:
      - total_activity_schedules: RoutineSchedules that should use activity_type
      - with_activity_type: have activity_type set (structured matching)
      - without_activity_type: rely on name fallback (TEMPORARY)
      - fallback_pct: percentage using fallback

    When fallback_pct < 5%, the name__icontains fallback can be removed.
    """
    from apps.life.models import RoutineSchedule

    # All schedules that match activity-related keywords
    activity_keywords = ['workout', 'exercise', 'journal', 'bible', 'faith',
                         'prayer', 'devotional']
    from django.db import models as _m
    q = _m.Q()
    for kw in activity_keywords:
        q |= _m.Q(name__icontains=kw)

    all_candidates = RoutineSchedule.objects.filter(is_active=True).filter(q)
    total = all_candidates.count()
    with_type = all_candidates.exclude(activity_type__isnull=True).exclude(activity_type='').count()
    without_type = total - with_type

    return {
        'total_activity_schedules': total,
        'with_activity_type': with_type,
        'without_activity_type': without_type,
        'fallback_pct': round(without_type / total * 100, 1) if total > 0 else 0.0,
    }


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

    _log, created = RoutineLog.objects.update_or_create(
        schedule=schedule,
        scheduled_date=target_date,
        defaults={
            'user': user,
            'log_status': 'skipped',
            'completed_at': None,
            'performed_at': None,
            'timing': '',
        },
    )
    if created:
        # routine_at_time is immutable — only set on creation, never on update.
        _log.routine_at_time = schedule.routine
        _log.save(update_fields=['routine_at_time'])
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
        from apps.core.utils import get_user_now, get_user_today
        user_now = get_user_now(user)
        user_today = get_user_today(user)

        for item in applicable:
            if item.id in completed_ids:
                continue  # already completed, leave it

            # Compute timing individually per item
            performed_at, timing = _compute_timing_and_performed_at(
                user, item, user_today, user_now,
            )
            if timing == 'late':
                batch_status = 'completed_late'
                as_scheduled = False
            else:
                batch_status = 'completed'
                as_scheduled = True

            existing = existing_logs.get(item.id)
            if existing:
                # Has a log (skipped, rescheduled, or other) — update to completed
                if existing.log_status == 'rescheduled':
                    batch_status = 'completed_late'
                    as_scheduled = False
                    performed_at = now
                    timing = RoutineLog.TIMING_LATE
                existing.log_status = batch_status
                existing.completed_at = now
                existing.completed_as_scheduled = as_scheduled
                existing.performed_at = performed_at
                existing.timing = timing
                existing.save(update_fields=[
                    'log_status', 'completed_at', 'completed_as_scheduled',
                    'performed_at', 'timing', 'updated_at',
                ])
            else:
                RoutineLog.objects.create(
                    user=user,
                    schedule=item,
                    scheduled_date=target_date,
                    log_status=batch_status,
                    completed_at=now,
                    completed_as_scheduled=as_scheduled,
                    performed_at=performed_at,
                    timing=timing,
                    routine_at_time=item.routine,
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
            routine_at_time=schedule.routine,
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


def get_log_routine(log):
    """Return the routine this log was executed under.

    Uses the write-time anchored routine_at_time field. Falls back to
    schedule.routine for pre-migration logs (routine_at_time is null).

    This is the ONLY correct way to determine a log's routine attribution.
    Do NOT use log.schedule.routine directly for historical queries — it
    reflects the schedule's CURRENT routine, which may differ if the item
    was moved.
    """
    return log.routine_at_time or log.schedule.routine


def get_log_routine_name(log):
    """Return the routine name this log was executed under.

    Convenience wrapper over get_log_routine() for contexts that only
    need the name string.
    """
    if log.routine_at_time_id:
        return log.routine_at_time.name
    return log.schedule.routine.name


@transaction.atomic
def move_routine_item(user, schedule, target_routine):
    """
    Move a RoutineSchedule from its current routine to a different routine.

    This affects FUTURE execution only. Historical RoutineLog records retain
    their routine_at_time (set at write time, immutable), so past attribution
    is never altered.

    The schedule keeps its same PK — all existing RoutineLog FK references
    remain valid. Only the schedule.routine FK changes.

    Args:
        user: User instance (must own both schedule and target_routine)
        schedule: RoutineSchedule instance to move
        target_routine: Routine instance to move the schedule into

    Returns:
        dict: {success: bool, from_routine: str, to_routine: str}

    Raises:
        ValueError: If validation fails (wrong owner, same routine, etc.)
    """
    from apps.life.models import Routine

    # ── Validation ──
    if schedule.routine.user_id != user.id:
        raise ValueError("Schedule does not belong to this user")
    if target_routine.user_id != user.id:
        raise ValueError("Target routine does not belong to this user")
    if schedule.routine_id == target_routine.id:
        raise ValueError("Schedule is already in this routine")
    if not target_routine.is_active or target_routine.status == 'deleted':
        raise ValueError("Target routine is not active")

    source_name = schedule.routine.name

    # ── Move: single FK update ──
    schedule.routine = target_routine
    schedule.save(update_fields=['routine'])

    # ── Cache invalidation ──
    # Future logs will have routine_at_time=target_routine via normal
    # creation paths. No backfill needed.
    try:
        from django.core.cache import cache
        cache.delete(f'wlj:user_state:{user.id}:routine')
        cache.delete(f'wlj:user_state:{user.id}:execution')
        cache.delete(f'wlj:cos_context:{user.id}')
    except Exception:
        pass  # Cache invalidation is best-effort

    logger.info(
        "ROUTINE_ITEM_MOVED user=%s schedule=%s (pk=%s) from='%s' to='%s' "
        "historical_logs=%d",
        user.id, schedule.name, schedule.pk, source_name,
        target_routine.name,
        schedule.logs.count(),
    )

    return {
        'success': True,
        'from_routine': source_name,
        'to_routine': target_routine.name,
        'item_name': schedule.name,
    }
