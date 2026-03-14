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
