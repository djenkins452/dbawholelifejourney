# ==============================================================================
# File: apps/health/signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Signal handlers for Health module calendar projections
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-14 (Architecture Evolution Phase 1)
# ==============================================================================
"""
Health Module Signals

Handles automatic calendar projection for medicine schedules and workout plans.
Part of the WLJ Architecture Evolution — projects commitment instances
into CalendarEngine for unified daily view.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='health.MedicineSchedule')
def handle_medicine_schedule_saved(sender, instance, **kwargs):
    """
    When a MedicineSchedule is saved, project it to the calendar engine.
    Creates a recurring CalendarEvent with commitment_level='non_negotiable'.
    """
    try:
        from apps.calendar_engine.services.projection import (
            upsert_from_medicine_schedule,
        )
        upsert_from_medicine_schedule(instance)
    except Exception as e:
        logger.warning(
            "Failed to project medicine schedule %s to calendar: %s",
            instance.pk, e,
        )


@receiver(post_delete, sender='health.MedicineSchedule')
def handle_medicine_schedule_deleted(sender, instance, **kwargs):
    """When a MedicineSchedule is deleted, remove its calendar events."""
    try:
        from apps.calendar_engine.services.projection import (
            delete_medicine_events,
        )
        delete_medicine_events(instance)
    except Exception as e:
        logger.warning(
            "Failed to clean up calendar events for medicine schedule %s: %s",
            instance.pk, e,
        )


@receiver(post_save, sender='health.WorkoutSchedule')
def handle_workout_schedule_saved(sender, instance, **kwargs):
    """
    When a WorkoutSchedule is saved, project it to the calendar engine.
    Creates a weekly recurring CalendarEvent for the workout day.
    """
    try:
        from apps.calendar_engine.services.projection import (
            upsert_from_workout_schedule,
        )
        upsert_from_workout_schedule(instance)
    except Exception as e:
        logger.warning(
            "Failed to project workout schedule %s to calendar: %s",
            instance.pk, e,
        )


@receiver(post_delete, sender='health.WorkoutSchedule')
def handle_workout_schedule_deleted(sender, instance, **kwargs):
    """When a WorkoutSchedule is deleted, remove its calendar events."""
    try:
        from apps.calendar_engine.services.projection import (
            delete_workout_events,
        )
        delete_workout_events(instance)
    except Exception as e:
        logger.warning(
            "Failed to clean up calendar events for workout schedule %s: %s",
            instance.pk, e,
        )


@receiver(post_save, sender='health.WorkoutSession')
def handle_workout_session_completed(sender, instance, **kwargs):
    """
    When a WorkoutSession is completed (completed_at set), create a
    WorkoutScheduleLog linking the session to its scheduled slot.

    Uses the shared status engine to determine completed vs completed_late.
    Idempotent — skips if a log already exists for this schedule+date.
    """
    if not instance.completed_at:
        return  # Not completed yet

    if not instance.from_template:
        return  # Ad-hoc workout, no schedule to match

    try:
        from apps.health.models import WorkoutPlan, WorkoutSchedule, WorkoutScheduleLog
        from apps.core.behavior.status_engine import compute_occurrence_status
        from datetime import datetime, timedelta

        user = instance.user
        workout_date = instance.date
        day_of_week = workout_date.weekday()

        # Find the active plan's schedule for this day + template
        active_plan = WorkoutPlan.objects.filter(
            user=user, is_active=True, status='active',
        ).first()
        if not active_plan:
            return

        matching_schedules = WorkoutSchedule.objects.filter(
            plan=active_plan,
            day_of_week=day_of_week,
            template=instance.from_template,
            is_rest_day=False,
        )

        if matching_schedules.count() == 0:
            return  # No matching schedule for this day/template
        elif matching_schedules.count() > 1:
            logger.warning(
                "WORKOUT_SCHEDULE_AMBIGUOUS user=%s date=%s template=%s matches=%d — skipping",
                user.id, workout_date, instance.from_template_id, matching_schedules.count(),
            )
            return

        schedule = matching_schedules.first()

        # Idempotency: skip if log already exists
        if WorkoutScheduleLog.objects.filter(
            schedule=schedule, scheduled_date=workout_date,
        ).exists():
            return

        # Compute status using shared engine
        from django.utils import timezone as _tz
        if schedule.preferred_time:
            scheduled_dt = _tz.make_aware(
                datetime.combine(workout_date, schedule.preferred_time),
                _tz.get_current_timezone(),
            )
        else:
            # No preferred time — treat as on-time by default
            scheduled_dt = instance.completed_at

        status = compute_occurrence_status(
            now=instance.completed_at,
            scheduled_datetime=scheduled_dt,
            grace_minutes=schedule.grace_period_minutes,
            log={'completed_at': instance.completed_at},
        )

        WorkoutScheduleLog.objects.create(
            user=user,
            schedule=schedule,
            scheduled_date=workout_date,
            log_status=status,  # 'completed' or 'completed_late'
            session=instance,
            completed_at=instance.completed_at,
        )

    except Exception as e:
        logger.warning(
            "Failed to create WorkoutScheduleLog for session %s: %s",
            instance.pk, e, exc_info=True,
        )
