# ==============================================================================
# File: apps/life/signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Signal handlers for the Life module
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Life Module Signals

Handles automatic actions when life models are created or updated:
- Task → Calendar projection (deadline markers + routine execution blocks)
- LifeEvent → Calendar projection
- Pet birthday SignificantEvent auto-creation
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='life.Pet')
def handle_pet_saved(sender, instance, created, **kwargs):
    """
    When a Pet is saved, create or update its birthday SignificantEvent.

    - Creates a birthday event if pet has birth_date
    - Converts birthday to memorial event if pet has passed
    - Removes event if birth_date is cleared
    """
    try:
        event = instance.create_or_update_birthday_event()
        if event:
            action = "Created" if created else "Updated"
            logger.debug(
                f"{action} birthday event for pet {instance.name}: "
                f"type={event.event_type}, date={event.event_date}"
            )
    except Exception as e:
        logger.warning(f"Failed to create birthday event for pet {instance.id}: {e}")


@receiver(post_save, sender='life.Task')
def handle_task_saved(sender, instance, created, **kwargs):
    """
    When any Task is saved, project it to the calendar engine:
    - Routine tasks (is_routine=True, scheduled_time): execution block + CoS prompts
    - Non-routine tasks with due_date: deadline marker
    - Tasks with no due_date: remove any existing marker

    This ensures all tasks with dates appear on the Time Command Center instantly.
    """
    if instance.is_routine and instance.scheduled_time and instance.due_date and not instance.is_completed:
        # Routine task — execution block + CoS prompts
        try:
            from apps.life.services.routine_service import RoutineTaskService
            RoutineTaskService.on_new_routine_task_created(instance)
        except Exception as e:
            logger.warning(
                "Failed to process routine task %s: %s", instance.pk, e
            )
    else:
        # All tasks (including routine without time) — deadline marker
        try:
            from apps.calendar_engine.services.projection import upsert_from_task
            upsert_from_task(instance)
        except Exception as e:
            logger.warning(
                "Failed to project task %s to calendar: %s", instance.pk, e
            )


@receiver(post_save, sender='life.LifeEvent')
def handle_life_event_saved(sender, instance, **kwargs):
    """
    When a LifeEvent is saved, project it to the calendar engine.
    Creates or updates a CalendarEvent with source_type=life_event.
    """
    try:
        from apps.calendar_engine.services.projection import upsert_from_life_event
        upsert_from_life_event(instance)
    except Exception as e:
        logger.warning(
            "Failed to project life event %s to calendar: %s",
            instance.pk, e,
        )


@receiver(post_delete, sender='life.Task')
def handle_task_deleted(sender, instance, **kwargs):
    """When a Task is hard-deleted, remove its calendar events."""
    try:
        from apps.calendar_engine.services.projection import delete_task_events
        delete_task_events(instance)
    except Exception as e:
        logger.warning(
            "Failed to clean up calendar events for task %s: %s",
            instance.pk, e
        )


@receiver(post_delete, sender='life.Pet')
def handle_pet_deleted(sender, instance, **kwargs):
    """
    When a Pet is deleted, remove its birthday SignificantEvent.
    """
    from .models import SignificantEvent

    try:
        deleted_count = SignificantEvent.objects.filter(
            user=instance.user,
            person_name__iexact=instance.name,
            event_type__in=['birthday', 'memorial'],
        ).delete()[0]

        if deleted_count > 0:
            logger.debug(f"Deleted birthday event for pet {instance.name}")
    except Exception as e:
        logger.warning(f"Failed to delete birthday event for pet {instance.id}: {e}")
