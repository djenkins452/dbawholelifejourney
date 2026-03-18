"""
Workout domain adapter for the behavior score contract.

Reads from WorkoutSchedule + WorkoutScheduleLog + WorkoutSession.
Uses the shared status engine for occurrence status computation.
"""

from datetime import timedelta

from apps.core.behavior.status_engine import build_behavior_output


def calculate_workout_behavior_output(user, start_date, end_date):
    """
    Produce the standardized behavior output contract for workouts.

    Expected = non-rest-day schedule entries for the date range.
    Completion data comes from WorkoutScheduleLog.

    Args:
        user: User instance
        start_date: date
        end_date: date

    Returns:
        dict matching behavior output contract, or None if no active plan
    """
    from apps.health.models import WorkoutPlan, WorkoutScheduleLog

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

    # Count expected workout days in the date range
    expected = 0
    day = start_date
    while day <= end_date:
        day_of_week = day.weekday()
        for entry in schedule_entries:
            if entry.applies_to_day(day_of_week):
                expected += 1
        day += timedelta(days=1)

    if expected == 0:
        return None

    # Count actual outcomes from WorkoutScheduleLog
    logs = WorkoutScheduleLog.objects.filter(
        user=user,
        scheduled_date__gte=start_date,
        scheduled_date__lte=end_date,
        schedule__plan=active_plan,
    )
    completed = logs.filter(log_status="completed").count()
    late = logs.filter(log_status="completed_late").count()
    skipped = logs.filter(log_status="skipped").count()

    # Missed = expected minus all accounted-for interactions
    accounted = completed + late + skipped
    missed = max(0, expected - accounted)

    return build_behavior_output(
        domain='workout',
        expected=expected,
        completed=completed,
        late=late,
        skipped=skipped,
        missed=missed,
    )
