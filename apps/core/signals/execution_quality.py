"""
Execution Quality Signal Generator.

Pure analytical layer — computes and stores execution quality for scheduled items.
Does NOT affect completion logic, CoS, Today Engine, or UI.

Quality states:
- ON_TARGET: completed within 15 minutes of scheduled time
- LATE: completed within 2 hours of scheduled time
- MISSED_WINDOW: completed but more than 2 hours late
- MISSED: not completed and more than 2 hours past scheduled time
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Timing windows ──
ON_TARGET_WINDOW = timedelta(minutes=15)
LATE_WINDOW = timedelta(hours=2)


def compute_execution_quality(scheduled_time, actual_time):
    """Compute execution quality from scheduled vs actual completion time.

    Args:
        scheduled_time: datetime when the item was scheduled
        actual_time: datetime when the item was actually completed

    Returns:
        str: One of 'on_target', 'late', 'missed_window'
    """
    from apps.core.signals.models import ExecutionSignal

    delta = actual_time - scheduled_time
    abs_delta = abs(delta)

    if abs_delta <= ON_TARGET_WINDOW:
        return ExecutionSignal.ON_TARGET
    elif delta <= LATE_WINDOW:
        return ExecutionSignal.LATE
    else:
        return ExecutionSignal.MISSED_WINDOW


def record_execution_signal(
    user, item_name, domain_type, scheduled_time, actual_time,
    date, source_model="", source_id=None,
):
    """Create or update an ExecutionSignal for a completed item.

    Uses update_or_create keyed on (user, item_name, domain_type, date)
    so re-completions update rather than duplicate.

    Args:
        user: User instance
        item_name: str name of the scheduled item
        domain_type: str domain (routine, workout, journal, medicine)
        scheduled_time: datetime when item was scheduled
        actual_time: datetime when item was completed
        date: date the signal applies to
        source_model: str name of the triggering model
        source_id: int PK of the triggering object

    Returns:
        ExecutionSignal instance, or None on error
    """
    from apps.core.signals.models import ExecutionSignal

    quality = compute_execution_quality(scheduled_time, actual_time)

    try:
        signal, _ = ExecutionSignal.objects.update_or_create(
            user=user,
            item_name=item_name,
            domain_type=domain_type,
            date=date,
            defaults={
                "scheduled_time": scheduled_time,
                "actual_time": actual_time,
                "execution_quality": quality,
                "source_model": source_model,
                "source_id": source_id,
            },
        )
        return signal
    except Exception:
        logger.warning(
            "Failed to record execution signal: user=%s item=%s domain=%s date=%s",
            user.pk, item_name, domain_type, date,
            exc_info=True,
        )
        return None


def record_missed_signal(
    user, item_name, domain_type, scheduled_time, date,
    source_model="", source_id=None,
):
    """Record a MISSED execution signal for an item that was not completed.

    Only creates the signal if one doesn't already exist for this item/day
    (a completion signal takes priority over a missed signal).

    Args:
        user: User instance
        item_name: str name of the scheduled item
        domain_type: str domain (routine, workout, journal, medicine)
        scheduled_time: datetime when item was scheduled
        date: date the signal applies to
        source_model: str name of the triggering model
        source_id: int PK of the triggering object

    Returns:
        ExecutionSignal instance, or None if already exists or on error
    """
    from apps.core.signals.models import ExecutionSignal

    try:
        signal, created = ExecutionSignal.objects.get_or_create(
            user=user,
            item_name=item_name,
            domain_type=domain_type,
            date=date,
            defaults={
                "scheduled_time": scheduled_time,
                "actual_time": None,
                "execution_quality": ExecutionSignal.MISSED,
                "source_model": source_model,
                "source_id": source_id,
            },
        )
        # Only return if we actually created the missed signal.
        # If a signal already exists (e.g., completed), don't overwrite.
        return signal if created else None
    except Exception:
        logger.warning(
            "Failed to record missed execution signal: user=%s item=%s domain=%s date=%s",
            user.pk, item_name, domain_type, date,
            exc_info=True,
        )
        return None


def record_signal_from_routine_log(routine_log):
    """Generate an ExecutionSignal from a RoutineLog completion.

    Derives scheduled_time from the RoutineSchedule, actual_time from
    RoutineLog.completed_at.
    """
    from datetime import datetime as dt

    if not routine_log.schedule_id:
        return None
    if not routine_log.performed_at and not routine_log.completed_at:
        return None

    schedule = routine_log.schedule
    if not schedule:
        return None

    # Build scheduled datetime from schedule.scheduled_time + log date
    try:
        scheduled_dt = timezone.make_aware(
            dt.combine(routine_log.scheduled_date, schedule.scheduled_time),
            timezone.get_current_timezone(),
        )
    except Exception:
        return None

    return record_execution_signal(
        user=routine_log.user,
        item_name=schedule.name,
        domain_type="routine",
        scheduled_time=scheduled_dt,
        actual_time=routine_log.performed_at or routine_log.completed_at,
        date=routine_log.scheduled_date,
        source_model="RoutineLog",
        source_id=routine_log.pk,
    )


def record_signal_from_workout_session(workout_session):
    """Generate an ExecutionSignal from a WorkoutSession completion.

    Looks for a matching RoutineSchedule with activity_type='workout'
    to get the scheduled time. If no schedule found, skips.
    """
    from datetime import datetime as dt

    if not workout_session.completed_at or not workout_session.date:
        return None

    try:
        from apps.life.models import RoutineSchedule

        day_of_week = workout_session.date.weekday()
        schedules = RoutineSchedule.objects.filter(
            routine__user=workout_session.user,
            routine__is_active=True,
            activity_type=RoutineSchedule.ACTIVITY_TYPE_WORKOUT,
            is_active=True,
            days_of_week__contains=str(day_of_week),
        )

        for schedule in schedules:
            scheduled_dt = timezone.make_aware(
                dt.combine(workout_session.date, schedule.scheduled_time),
                timezone.get_current_timezone(),
            )
            record_execution_signal(
                user=workout_session.user,
                item_name=schedule.name,
                domain_type="workout",
                scheduled_time=scheduled_dt,
                actual_time=workout_session.completed_at,
                date=workout_session.date,
                source_model="WorkoutSession",
                source_id=workout_session.pk,
            )
    except Exception:
        logger.warning(
            "Failed to generate execution signal from WorkoutSession %s",
            workout_session.pk, exc_info=True,
        )
    return None


def record_signal_from_journal_entry(journal_entry):
    """Generate an ExecutionSignal from a JournalEntry creation.

    Looks for a matching RoutineSchedule with activity_type='journal'
    to get the scheduled time.
    """
    from datetime import datetime as dt

    if not journal_entry.entry_date:
        return None

    try:
        from apps.life.models import RoutineSchedule

        day_of_week = journal_entry.entry_date.weekday()
        schedules = RoutineSchedule.objects.filter(
            routine__user=journal_entry.user,
            routine__is_active=True,
            activity_type=RoutineSchedule.ACTIVITY_TYPE_JOURNAL,
            is_active=True,
            days_of_week__contains=str(day_of_week),
        )

        for schedule in schedules:
            scheduled_dt = timezone.make_aware(
                dt.combine(journal_entry.entry_date, schedule.scheduled_time),
                timezone.get_current_timezone(),
            )
            record_execution_signal(
                user=journal_entry.user,
                item_name=schedule.name,
                domain_type="journal",
                scheduled_time=scheduled_dt,
                actual_time=journal_entry.created_at,
                date=journal_entry.entry_date,
                source_model="JournalEntry",
                source_id=journal_entry.pk,
            )
    except Exception:
        logger.warning(
            "Failed to generate execution signal from JournalEntry %s",
            journal_entry.pk, exc_info=True,
        )
    return None


def record_signal_from_medicine_log(medicine_log):
    """Generate an ExecutionSignal from a MedicineLog completion.

    Uses MedicineLog.scheduled_time and taken_at directly.
    """
    from datetime import datetime as dt

    if not medicine_log.taken_at or not medicine_log.scheduled_time:
        return None

    try:
        scheduled_dt = timezone.make_aware(
            dt.combine(medicine_log.scheduled_date, medicine_log.scheduled_time),
            timezone.get_current_timezone(),
        )
        medicine_name = str(medicine_log.intake) if medicine_log.intake else "Unknown"

        return record_execution_signal(
            user=medicine_log.user,
            item_name=medicine_name,
            domain_type="medicine",
            scheduled_time=scheduled_dt,
            actual_time=medicine_log.taken_at,
            date=medicine_log.scheduled_date,
            source_model="MedicineLog",
            source_id=medicine_log.pk,
        )
    except Exception:
        logger.warning(
            "Failed to generate execution signal from MedicineLog %s",
            medicine_log.pk, exc_info=True,
        )
        return None
