"""
Routine domain — PUBLIC service interface.

This is the ONLY module that views and external code should import for
routine operations. It exposes:
  - toggle_routine_completion()  — toggle a schedule item's completion
  - skip_routine()               — mark a schedule item as skipped

For reading routine state (items, windows, summaries), use:
  apps.core.ai_state.state_builder.build_routine_state()

Internal computation lives in _routine_internal.py — do NOT import
that module from views or other services.

Status transition rules (strict execution model):
  - One RoutineLog per schedule per day (enforced by unique_together)
  - none → completed  (toggle: first check)
  - completed → none  (toggle: un-check, deletes log)
  - skipped → completed  (toggle: re-check a skipped item)
  - none → skipped  (explicit skip action)
  - Missed is COMPUTED, not stored (absence of log + time past grace)
  - No auto-complete — completion is explicit only
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def toggle_routine_completion(user, schedule, target_date):
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

    Returns:
        dict: {status: str, is_completed: bool}
    """
    from apps.life.models import RoutineLog

    existing_log = RoutineLog.objects.filter(
        schedule=schedule, scheduled_date=target_date,
    ).first()

    if existing_log:
        if existing_log.log_status in ('completed', 'completed_late'):
            existing_log.delete()
            return {'status': 'pending', 'is_completed': False}
        elif existing_log.log_status == 'skipped':
            existing_log.log_status = 'completed'
            existing_log.completed_at = timezone.now()
            existing_log.save(update_fields=['log_status', 'completed_at', 'updated_at'])
            return {'status': 'completed', 'is_completed': True}
        else:
            return {'status': existing_log.log_status, 'is_completed': False}
    else:
        RoutineLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=target_date,
            log_status='completed',
            completed_at=timezone.now(),
        )
        return {'status': 'completed', 'is_completed': True}


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
