"""
Routine domain adapter for the behavior score contract.

Reads from Routine/RoutineSchedule/RoutineLog models.
Built to contract spec from day one.
"""

from datetime import timedelta

from apps.core.behavior.status_engine import build_behavior_output


def calculate_routine_behavior_output(user, start_date, end_date):
    """
    Produce the standardized behavior output contract for routines.

    Expected = active routine schedule items that apply to each day in range.
    Completion data comes from RoutineLog.

    Args:
        user: User instance
        start_date: date
        end_date: date

    Returns:
        dict matching behavior output contract, or None if no routines
    """
    from apps.life.models import Routine, RoutineLog, RoutineSchedule

    active_routines = Routine.objects.filter(
        user=user, is_active=True, status='active',
    ).prefetch_related('items')

    if not active_routines.exists():
        return None

    # Gather all active schedule items
    all_items = []
    for routine in active_routines:
        all_items.extend(routine.items.filter(is_active=True))

    if not all_items:
        return None

    # Count expected occurrences in the date range
    expected = 0
    day = start_date
    while day <= end_date:
        day_of_week = day.weekday()
        for item in all_items:
            if item.specific_date:
                if item.specific_date == day:
                    expected += 1
            elif item.applies_to_day(day_of_week):
                expected += 1
        day += timedelta(days=1)

    if expected == 0:
        return None

    # Count actual outcomes from RoutineLog
    schedule_ids = [item.id for item in all_items]
    logs = RoutineLog.objects.filter(
        user=user,
        schedule_id__in=schedule_ids,
        scheduled_date__gte=start_date,
        scheduled_date__lte=end_date,
    )
    completed = logs.filter(log_status="completed").count()
    late = logs.filter(log_status="completed_late").count()
    skipped = logs.filter(log_status="skipped").count()

    accounted = completed + late + skipped
    missed = max(0, expected - accounted)

    return build_behavior_output(
        domain='routine',
        expected=expected,
        completed=completed,
        late=late,
        skipped=skipped,
        missed=missed,
    )
