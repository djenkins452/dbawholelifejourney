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
