"""
Behavior Correction Service — allows users to edit past scheduled items.

Core rules:
  - Logs are the single source of truth
  - Missed is NEVER stored — always computed as absence
  - User-selected status is final truth (no re-evaluation on correction)
  - End-of-day does NOT lock data
  - Behavior score recomputes from scratch after any edit

Supports all three behavioral domains: medication, workout, routine.
"""

import logging
from datetime import date

from django.utils import timezone

logger = logging.getLogger(__name__)

# Valid statuses a user can set when correcting a past log
VALID_CORRECTION_STATUSES = {
    'medication': {'taken', 'late', 'skipped'},
    'workout': {'completed', 'completed_late', 'skipped'},
    'routine': {'completed', 'completed_late', 'skipped'},
}


def correct_medication_log(user, medicine_id, schedule_id, scheduled_date, new_status):
    """
    Create or update a MedicineLog for a past date.

    When user marks as 'taken' or 'late', their selection is final —
    we do NOT re-evaluate based on timestamp.

    Args:
        user: User instance
        medicine_id: int — Medicine PK
        schedule_id: int — MedicineSchedule PK
        scheduled_date: date
        new_status: str — 'taken', 'late', or 'skipped'

    Returns:
        dict with success/error + log data
    """
    if new_status not in VALID_CORRECTION_STATUSES['medication']:
        return {'success': False, 'error': f'Invalid status: {new_status}'}

    from apps.health.models import Medicine, MedicineLog, MedicineSchedule

    try:
        medicine = Medicine.objects.get(pk=medicine_id, user=user)
        schedule = MedicineSchedule.objects.get(pk=schedule_id, medicine=medicine)
    except (Medicine.DoesNotExist, MedicineSchedule.DoesNotExist):
        return {'success': False, 'error': 'Medicine or schedule not found'}

    # Create or update — unique on (medicine, schedule, scheduled_date)
    log, created = MedicineLog.objects.update_or_create(
        user=user,
        medicine=medicine,
        schedule=schedule,
        scheduled_date=scheduled_date,
        defaults={
            'log_status': new_status,
            'scheduled_time': schedule.scheduled_time,
            'taken_at': timezone.now() if new_status in ('taken', 'late') else None,
            'is_user_corrected': True,
        },
    )

    logger.info(
        "BEHAVIOR_CORRECTION domain=medication user=%s medicine=%s date=%s "
        "status=%s created=%s",
        user.id, medicine_id, scheduled_date, new_status, created,
    )

    return {
        'success': True,
        'log_id': log.pk,
        'created': created,
        'status': new_status,
    }


def correct_workout_log(user, schedule_id, scheduled_date, new_status, session_id=None):
    """
    Create or update a WorkoutScheduleLog for a past date.

    When user marks as 'completed' or 'completed_late', their selection is final.

    Args:
        user: User instance
        schedule_id: int — WorkoutSchedule PK
        scheduled_date: date
        new_status: str — 'completed', 'completed_late', or 'skipped'
        session_id: int or None — WorkoutSession PK (required for completed/completed_late)

    Returns:
        dict with success/error + log data
    """
    if new_status not in VALID_CORRECTION_STATUSES['workout']:
        return {'success': False, 'error': f'Invalid status: {new_status}'}

    from apps.health.models import WorkoutSchedule, WorkoutScheduleLog, WorkoutSession

    try:
        schedule = WorkoutSchedule.objects.get(pk=schedule_id, plan__user=user)
    except WorkoutSchedule.DoesNotExist:
        return {'success': False, 'error': 'Workout schedule not found'}

    session = None
    if new_status in ('completed', 'completed_late'):
        if session_id:
            try:
                session = WorkoutSession.objects.get(pk=session_id, user=user)
            except WorkoutSession.DoesNotExist:
                return {'success': False, 'error': 'Workout session not found'}

    log, created = WorkoutScheduleLog.objects.update_or_create(
        user=user,
        schedule=schedule,
        scheduled_date=scheduled_date,
        defaults={
            'log_status': new_status,
            'session': session,
            'completed_at': timezone.now() if new_status != 'skipped' else None,
            'is_user_corrected': True,
        },
    )

    logger.info(
        "BEHAVIOR_CORRECTION domain=workout user=%s schedule=%s date=%s "
        "status=%s created=%s",
        user.id, schedule_id, scheduled_date, new_status, created,
    )

    return {
        'success': True,
        'log_id': log.pk,
        'created': created,
        'status': new_status,
    }


def correct_routine_log(user, schedule_id, scheduled_date, new_status):
    """
    Create or update a RoutineLog for a past date.

    When user marks as 'completed' or 'completed_late', their selection is final.

    Args:
        user: User instance
        schedule_id: int — RoutineSchedule PK
        scheduled_date: date
        new_status: str — 'completed', 'completed_late', or 'skipped'

    Returns:
        dict with success/error + log data
    """
    if new_status not in VALID_CORRECTION_STATUSES['routine']:
        return {'success': False, 'error': f'Invalid status: {new_status}'}

    from apps.life.models import RoutineLog, RoutineSchedule

    try:
        schedule = RoutineSchedule.objects.get(
            pk=schedule_id, routine__user=user,
        )
    except RoutineSchedule.DoesNotExist:
        return {'success': False, 'error': 'Routine schedule not found'}

    log, created = RoutineLog.objects.update_or_create(
        user=user,
        schedule=schedule,
        scheduled_date=scheduled_date,
        defaults={
            'log_status': new_status,
            'completed_at': timezone.now() if new_status != 'skipped' else None,
            'is_user_corrected': True,
        },
    )

    logger.info(
        "BEHAVIOR_CORRECTION domain=routine user=%s schedule=%s date=%s "
        "status=%s created=%s",
        user.id, schedule_id, scheduled_date, new_status, created,
    )

    return {
        'success': True,
        'log_id': log.pk,
        'created': created,
        'status': new_status,
    }


def get_scheduled_items_for_date(user, target_date):
    """
    Get all scheduled behavioral items for a specific date with their current status.

    Returns a list of items across all domains, suitable for UI display.
    Each item includes the schedule info and current log status (or 'missed').
    """
    items = []

    day_of_week = target_date.weekday()
    today = timezone.now().date()

    # ── Medication ──
    try:
        from apps.health.models import Medicine, MedicineLog

        active_meds = Medicine.objects.filter(
            user=user, medicine_status='active',
        ).prefetch_related('schedules')

        for med in active_meds:
            for sched in med.schedules.filter(is_active=True):
                if sched.applies_to_day(day_of_week):
                    log = MedicineLog.objects.filter(
                        user=user, medicine=med, schedule=sched,
                        scheduled_date=target_date,
                    ).first()
                    items.append({
                        'domain': 'medication',
                        'entity_name': med.name,
                        'schedule_id': sched.pk,
                        'entity_id': med.pk,
                        'scheduled_time': str(sched.scheduled_time) if sched.scheduled_time else None,
                        'time_of_day': sched.time_of_day,
                        'status': log.log_status if log else ('missed' if target_date < today else 'pending'),
                        'log_id': log.pk if log else None,
                        'is_user_corrected': log.is_user_corrected if log else False,
                    })
    except Exception as e:
        logger.warning("get_scheduled_items_for_date medication error: %s", e)

    # ── Workout ──
    try:
        from apps.health.models import WorkoutPlan, WorkoutScheduleLog

        active_plan = WorkoutPlan.objects.filter(
            user=user, is_active=True, status='active',
        ).prefetch_related('schedule_entries').first()

        if active_plan:
            for sched in active_plan.schedule_entries.filter(is_rest_day=False):
                if sched.applies_to_day(day_of_week):
                    log = WorkoutScheduleLog.objects.filter(
                        user=user, schedule=sched, scheduled_date=target_date,
                    ).first()
                    items.append({
                        'domain': 'workout',
                        'entity_name': str(sched.template.name) if sched.template else str(sched),
                        'schedule_id': sched.pk,
                        'entity_id': sched.template_id,
                        'scheduled_time': str(sched.preferred_time) if sched.preferred_time else None,
                        'time_of_day': None,
                        'status': log.log_status if log else ('missed' if target_date < today else 'pending'),
                        'log_id': log.pk if log else None,
                        'is_user_corrected': log.is_user_corrected if log else False,
                    })
    except Exception as e:
        logger.warning("get_scheduled_items_for_date workout error: %s", e)

    # ── Routine ──
    try:
        from apps.life.models import Routine, RoutineLog

        active_routines = Routine.objects.filter(
            user=user, is_active=True, status='active',
        ).prefetch_related('items')

        for routine in active_routines:
            for sched in routine.items.filter(is_active=True):
                applies = False
                if sched.specific_date:
                    applies = sched.specific_date == target_date
                else:
                    applies = sched.applies_to_day(day_of_week)

                if applies:
                    log = RoutineLog.objects.filter(
                        user=user, schedule=sched, scheduled_date=target_date,
                    ).first()
                    items.append({
                        'domain': 'routine',
                        'entity_name': sched.name,
                        'schedule_id': sched.pk,
                        'entity_id': routine.pk,
                        'scheduled_time': str(sched.scheduled_time) if sched.scheduled_time else None,
                        'time_of_day': routine.time_of_day,
                        'status': log.log_status if log else ('missed' if target_date < today else 'pending'),
                        'log_id': log.pk if log else None,
                        'is_user_corrected': log.is_user_corrected if log else False,
                    })
    except Exception as e:
        logger.warning("get_scheduled_items_for_date routine error: %s", e)

    # Sort by scheduled_time
    items.sort(key=lambda x: x.get('scheduled_time') or '99:99')
    return items
