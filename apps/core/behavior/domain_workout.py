"""
Workout domain adapter for the behavior score contract.

Reads from WorkoutSchedule + WorkoutScheduleLog + WorkoutSession + RoutineLog.
Uses the shared status engine for occurrence status computation.

Completion sources (checked in order):
  1. WorkoutScheduleLog (direct schedule adherence log)
  2. WorkoutSession (any completed session for that date)
  3. RoutineLog (routine item with obligation_type='workout' or name match)

A day is "completed" if ANY of these sources records a completion.

Fairness rule: today's workouts scheduled after the current time are excluded
from expected count. You can't miss a workout that isn't due yet.
"""

import logging
from datetime import timedelta

from apps.core.behavior.status_engine import build_behavior_output

logger = logging.getLogger(__name__)


def calculate_workout_behavior_output(user, start_date, end_date):
    """
    Produce the standardized behavior output contract for workouts.

    Expected = non-rest-day schedule entries for the date range.
    Completion data comes from WorkoutScheduleLog, WorkoutSession,
    and RoutineLog (routine items marked as workout obligations).

    Args:
        user: User instance
        start_date: date
        end_date: date

    Returns:
        dict matching behavior output contract, or None if no active plan
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import WorkoutPlan, WorkoutScheduleLog, WorkoutSession

    active_plan = WorkoutPlan.objects.filter(
        user=user, is_active=True, status='active',
    ).prefetch_related('schedule_entries').first()

    if not active_plan:
        return None

    schedule_entries = list(
        active_plan.schedule_entries.filter(is_rest_day=False)
    )
    if not schedule_entries:
        return None

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()

    # Count expected workout days in the date range.
    # For today: only count workouts whose preferred_time has passed.
    # You can't miss a workout that isn't due yet.
    expected_days = set()
    day = start_date
    while day <= end_date:
        day_of_week = day.weekday()
        is_today = (day == user_today)
        for entry in schedule_entries:
            if entry.applies_to_day(day_of_week):
                if is_today and entry.preferred_time and entry.preferred_time > current_time:
                    # Future workout today — not due yet, skip
                    continue
                expected_days.add(day)
        day += timedelta(days=1)

    expected = len(expected_days)
    if expected == 0:
        return None

    # ── Source 1: WorkoutScheduleLog (direct schedule adherence) ──
    schedule_logs = WorkoutScheduleLog.objects.filter(
        user=user,
        scheduled_date__gte=start_date,
        scheduled_date__lte=end_date,
        schedule__plan=active_plan,
    )
    log_completed_dates = set(
        schedule_logs.filter(
            log_status__in=["completed", "completed_late"],
        ).values_list('scheduled_date', flat=True)
    )
    log_skipped_dates = set(
        schedule_logs.filter(
            log_status="skipped",
        ).values_list('scheduled_date', flat=True)
    )

    # ── Source 2: WorkoutSession (any completed session for that date) ──
    session_dates = set(
        WorkoutSession.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
            completed_at__isnull=False,
        ).values_list('date', flat=True)
    )

    # ── Source 3: RoutineLog (workout obligation items) ──
    routine_dates = set()
    try:
        from apps.life.models import RoutineLog, RoutineSchedule
        workout_routine_logs = RoutineLog.objects.filter(
            schedule__routine__user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
            log_status__in=[
                RoutineLog.STATUS_COMPLETED,
                RoutineLog.STATUS_COMPLETED_LATE,
            ],
        ).filter(
            # Match by structural obligation_type OR name-based fallback
            schedule__obligation_type='workout',
        ).values_list('scheduled_date', flat=True)
        routine_dates = set(workout_routine_logs)

        # Name-based fallback for items without obligation_type set
        if not routine_dates:
            from apps.core.execution.execution_truth_engine import WORKOUT_NAMES
            from django.db.models.functions import Lower
            name_matched_logs = RoutineLog.objects.filter(
                schedule__routine__user=user,
                scheduled_date__gte=start_date,
                scheduled_date__lte=end_date,
                log_status__in=[
                    RoutineLog.STATUS_COMPLETED,
                    RoutineLog.STATUS_COMPLETED_LATE,
                ],
            ).annotate(
                name_lower=Lower('schedule__name'),
            ).filter(
                name_lower__in=WORKOUT_NAMES,
            ).values_list('scheduled_date', flat=True)
            routine_dates = set(name_matched_logs)
    except Exception:
        logger.debug("Workout behavior: routine log check failed", exc_info=True)

    # ── Merge all sources ──
    # A day is completed if ANY source records completion
    all_completed_dates = (log_completed_dates | session_dates | routine_dates) & expected_days
    all_skipped_dates = log_skipped_dates - all_completed_dates  # skip only if not completed

    completed = len(all_completed_dates)
    skipped = len(all_skipped_dates)
    late = 0  # late is already included in completed dates from schedule_logs
    missed = max(0, expected - completed - skipped)

    return build_behavior_output(
        domain='workout',
        expected=expected,
        completed=completed,
        late=late,
        skipped=skipped,
        missed=missed,
    )
