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


@receiver(post_save, sender='health.IntakeSchedule')
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


@receiver(post_delete, sender='health.IntakeSchedule')
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
    When a WorkoutSession is saved:

    Block 1 — WorkoutScheduleLog: If completed_at AND from_template, create
    a WorkoutScheduleLog linking the session to its workout plan schedule slot.

    Block 2 — Routine auto-complete: If date is set (any workout, including
    ad-hoc), auto-complete matching RoutineSchedule items for that day.
    Uses started_at (preferred) > completed_at > now for timeliness.
    First-workout-wins: once a routine log exists for the day, later workouts
    are no-ops.
    """
    # ── Block 1: WorkoutScheduleLog ──
    # Creates schedule adherence records when a workout is completed.
    # Two paths:
    #   A) Template-linked: match by day_of_week + template (precise)
    #   B) Any workout on a scheduled day: match by day_of_week only (fallback)
    # This ensures workouts logged via routine, ad-hoc, or any other path
    # still count toward workout plan adherence.
    if instance.completed_at and instance.date:
        try:
            from apps.health.models import WorkoutPlan, WorkoutSchedule, WorkoutScheduleLog
            from apps.core.behavior.status_engine import compute_occurrence_status
            from datetime import datetime, timedelta

            user = instance.user
            workout_date = instance.date
            day_of_week = workout_date.weekday()

            active_plan = WorkoutPlan.objects.filter(
                user=user, is_active=True, status='active',
            ).first()
            if active_plan:
                # Path A: template-linked (precise match)
                if instance.from_template:
                    matching_schedules = WorkoutSchedule.objects.filter(
                        plan=active_plan,
                        day_of_week=day_of_week,
                        template=instance.from_template,
                        is_rest_day=False,
                    )
                else:
                    # Path B: no template — match any non-rest schedule for this day
                    matching_schedules = WorkoutSchedule.objects.filter(
                        plan=active_plan,
                        day_of_week=day_of_week,
                        is_rest_day=False,
                    )

                if matching_schedules.count() == 1:
                    schedule = matching_schedules.first()

                    if not WorkoutScheduleLog.objects.filter(
                        schedule=schedule, scheduled_date=workout_date,
                    ).exists():
                        from django.utils import timezone as _tz
                        if schedule.preferred_time:
                            scheduled_dt = _tz.make_aware(
                                datetime.combine(workout_date, schedule.preferred_time),
                                _tz.get_current_timezone(),
                            )
                        else:
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
                            log_status=status,
                            session=instance,
                            completed_at=instance.completed_at,
                        )
                elif matching_schedules.count() > 1:
                    if instance.from_template:
                        logger.warning(
                            "WORKOUT_SCHEDULE_AMBIGUOUS user=%s date=%s template=%s matches=%d — skipping",
                            user.id, workout_date, instance.from_template_id, matching_schedules.count(),
                        )
                    else:
                        # Multiple schedule slots for this day and no template to disambiguate.
                        # Pick the first unlogged slot to avoid over-counting.
                        for schedule in matching_schedules:
                            if not WorkoutScheduleLog.objects.filter(
                                schedule=schedule, scheduled_date=workout_date,
                            ).exists():
                                from django.utils import timezone as _tz
                                if schedule.preferred_time:
                                    scheduled_dt = _tz.make_aware(
                                        datetime.combine(workout_date, schedule.preferred_time),
                                        _tz.get_current_timezone(),
                                    )
                                else:
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
                                    log_status=status,
                                    session=instance,
                                    completed_at=instance.completed_at,
                                )
                                break  # one session fills one slot

        except Exception as e:
            logger.warning(
                "Failed to create WorkoutScheduleLog for session %s: %s",
                instance.pk, e, exc_info=True,
            )

    # ── Block 2: Auto-complete matching RoutineSchedule items ──
    # Fires for ANY workout with a date (including ad-hoc, no template).
    # Uses started_at (preferred) > completed_at > now for timeliness,
    # because routine adherence is about when the activity BEGAN.
    #
    # Threshold gate: aggregate all completed workouts for the day and only
    # trigger routine completion when total duration >= threshold minutes.
    # This prevents a 5-minute walk from marking the workout routine done,
    # while allowing multiple short workouts to aggregate past the threshold.
    if instance.date:
        try:
            from django.db.models import Sum as _Sum

            from apps.health.models import WorkoutSession
            from apps.health.services.fitness_utils import ROUTINE_COMPLETION_THRESHOLD_MINUTES
            from apps.life.services.routine_helpers import auto_complete_routine_schedules

            total_today = (
                WorkoutSession.objects.filter(
                    user=instance.user,
                    date=instance.date,
                    completed_at__isnull=False,
                )
                .exclude(status="deleted")
                .aggregate(total=_Sum("duration_minutes"))["total"]
                or 0
            )

            if total_today >= ROUTINE_COMPLETION_THRESHOLD_MINUTES:
                # Prefer start time for timeliness classification
                effective_time = instance.started_at or instance.completed_at

                results = auto_complete_routine_schedules(
                    user=instance.user,
                    keyword='workout',
                    source='workout',
                    completion_time=effective_time,
                    source_object_id=instance.pk,
                    target_date=instance.date,
                )
                if results:
                    logger.info(
                        "WORKOUT_ROUTINE_AUTOCOMPLETE user=%s date=%s matched=%d session=%s total_min=%d",
                        instance.user_id, instance.date, len(results), instance.pk, total_today,
                    )
            else:
                logger.debug(
                    "WORKOUT_ROUTINE_THRESHOLD_NOT_MET user=%s date=%s total_min=%d threshold=%d",
                    instance.user_id, instance.date, total_today, ROUTINE_COMPLETION_THRESHOLD_MINUTES,
                )
        except Exception as e:
            logger.warning(
                "Failed to auto-complete routine schedules for workout %s: %s",
                instance.pk, e, exc_info=True,
            )
