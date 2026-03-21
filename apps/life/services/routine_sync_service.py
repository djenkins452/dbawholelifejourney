"""
Routine ↔ Maintenance Sync Service

Handles the auto-sync when a MaintenanceLog is created from a routine
completion. Updates:
  1. RoutineSchedule.last_maintenance_date
  2. RoutineLog.maintenance_logged = True

No FK between systems. No RoutineLog history rewriting.
RoutineSchedule remains the source of scheduling truth.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def sync_routine_from_maintenance(schedule, maintenance_log, user):
    """
    Sync a RoutineSchedule after a MaintenanceLog was created from it.

    Args:
        schedule: RoutineSchedule instance
        maintenance_log: MaintenanceLog instance (just saved)
        user: Django User instance

    Updates:
        - schedule.last_maintenance_date = maintenance_log.date
        - Today's RoutineLog.maintenance_logged = True
        - maintenance_log.matched_schedule_id = schedule.pk
    """
    from apps.life.models import RoutineLog
    from apps.core.utils import get_user_today

    today = get_user_today(user)

    # 1. Update schedule's last maintenance date
    schedule.last_maintenance_date = maintenance_log.date
    schedule.save(update_fields=['last_maintenance_date'])

    # 2. Mark today's RoutineLog as maintenance_logged
    try:
        routine_log = RoutineLog.objects.get(
            schedule=schedule,
            scheduled_date=today,
        )
        if not routine_log.maintenance_logged:
            routine_log.maintenance_logged = True
            routine_log.save(update_fields=['maintenance_logged'])
    except RoutineLog.DoesNotExist:
        # No log for today — routine may not have been completed today
        logger.debug(
            "No RoutineLog found for schedule=%s date=%s — skipping maintenance_logged flag",
            schedule.pk, today,
        )

    # 3. Set soft reference on maintenance log
    if not maintenance_log.matched_schedule_id:
        maintenance_log.matched_schedule_id = schedule.pk
        maintenance_log.save(update_fields=['matched_schedule_id'])

    logger.info(
        "ROUTINE_MAINTENANCE_SYNC schedule=%s maintenance_log=%s date=%s",
        schedule.pk, maintenance_log.pk, maintenance_log.date,
    )
