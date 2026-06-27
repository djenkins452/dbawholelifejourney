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


@receiver(post_save, sender='health.Intake')
def handle_intake_created(sender, instance, created, **kwargs):
    """When an Intake is first created, append the canonical 'started' event to
    the MedicationEvent ledger (Sprint 2A). Captures every creation path — web
    form, AI, scan-confirm, admin — via one hook. History logging is best-effort
    and must never block the create."""
    if not created:
        return
    try:
        from apps.health.medication_events import record_medication_change
        from apps.health.models import MedicationEvent
        record_medication_change(
            instance,
            MedicationEvent.EVENT_STARTED,
            source=MedicationEvent.SOURCE_LIFECYCLE,
            new_value={"name": instance.name, "dose": instance.dose},
            effective_date=instance.start_date,
        )
    except Exception as e:  # pragma: no cover - additive history, never blocking
        logger.warning(
            "Failed to record 'started' MedicationEvent for intake %s: %s",
            instance.pk, e,
        )


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


@receiver(post_save, sender='health.WeightEntry')
def resolve_stale_weight_insights_on_new_entry(sender, instance, created, **kwargs):
    """When a fresh WeightEntry arrives the 'missing_weight_logging'
    insight's condition no longer holds. The PIE rule that produced it
    only runs on scheduled_check events (not record_created), so without
    explicit dismissal here the stale insight would persist in the
    dashboard accountability layer while Beth (reading SAE) is fresh.
    Delegates to the canonical weight_sync resolver — single dismissal path.
    """
    if not created:
        return
    try:
        from apps.health.services.weight_sync import resolve_weight_gap_insights
        resolve_weight_gap_insights(instance.user)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "weight insight resolve on save failed: %s", e, exc_info=True,
        )


@receiver(post_save, sender='health.WeightEntry')
def evaluate_objective_weight_milestones_on_save(sender, instance, **kwargs):
    """Phase 1 — bidirectional weight milestone convergence.

    Every WeightEntry write (create OR update) re-evaluates the user's
    objective weight milestones so the goal layer reflects reality
    immediately. The evaluator filters on objective_metric="weight_lb"
    + objective_operator="lte" so achievement milestones are never
    touched.

    Fires on both create AND update so a weight CORRECTION also
    converges. Idempotent on the evaluator side (no DB write if state
    already matches). Fail-soft: never raises into the caller —
    WeightEntry.save() is the trust contract here.
    """
    if not instance.user_id:
        return
    try:
        from apps.purpose.services.objective_weight_milestones import (
            evaluate_weight_milestones,
        )
        evaluate_weight_milestones(instance.user)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "objective weight milestone re-eval skipped "
            "(user=%s entry=%s): %s",
            instance.user_id, instance.id, e, exc_info=True,
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
    # Qualification gate — a day's workouts qualify for routine auto-complete
    # when EITHER:
    #   (a) any completed session has logged workout_exercises (real work
    #       was tracked — sets/reps), OR
    #   (b) total duration across completed sessions >= threshold minutes
    #       (covers activity-mode sessions like "Pickleball 30 min" that
    #       have no exercise rows).
    # Rationale: structured strength sessions routinely leave
    # duration_minutes at 0/null — the user never starts a timer — but
    # clearly represent a real workout. The duration threshold remains
    # the guardrail for activity-mode sessions so a 5-minute walk still
    # doesn't mark the workout routine done.
    if instance.date:
        try:
            from django.db.models import Sum as _Sum

            from apps.health.models import WorkoutSession
            from apps.health.services.fitness_utils import ROUTINE_COMPLETION_THRESHOLD_MINUTES
            from apps.life.services.routine_helpers import auto_complete_routine_schedules

            completed_qs = (
                WorkoutSession.objects
                .filter(
                    user=instance.user,
                    date=instance.date,
                    completed_at__isnull=False,
                )
                .exclude(status="deleted")
            )

            total_today = (
                completed_qs.aggregate(total=_Sum("duration_minutes"))["total"]
                or 0
            )
            has_logged_exercises = completed_qs.filter(
                workout_exercises__isnull=False,
            ).exists()

            qualifies = (
                has_logged_exercises
                or total_today >= ROUTINE_COMPLETION_THRESHOLD_MINUTES
            )

            if qualifies:
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
                        "WORKOUT_ROUTINE_AUTOCOMPLETE user=%s date=%s "
                        "matched=%d session=%s total_min=%d exercises=%s",
                        instance.user_id, instance.date, len(results),
                        instance.pk, total_today, has_logged_exercises,
                    )
            else:
                logger.debug(
                    "WORKOUT_ROUTINE_NOT_QUALIFIED user=%s date=%s "
                    "total_min=%d threshold=%d exercises=%s",
                    instance.user_id, instance.date, total_today,
                    ROUTINE_COMPLETION_THRESHOLD_MINUTES, has_logged_exercises,
                )
        except Exception as e:
            logger.warning(
                "Failed to auto-complete routine schedules for workout %s: %s",
                instance.pk, e, exc_info=True,
            )
