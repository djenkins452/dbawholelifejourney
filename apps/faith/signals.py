# ==============================================================================
# File: apps/faith/signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Signal handlers for Faith module calendar projections
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-14 (Architecture Evolution Phase 1)
# ==============================================================================
"""
Faith Module Signals

Handles automatic calendar projection for Bible reading plans.
Part of the WLJ Architecture Evolution — projects commitment instances
into CalendarEngine for unified daily view.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='faith.UserReadingPlan')
def handle_reading_plan_saved(sender, instance, **kwargs):
    """
    When a UserReadingPlan is saved, project it to the calendar engine.
    Creates a recurring CalendarEvent for daily Bible reading.
    """
    try:
        from apps.calendar_engine.services.projection import (
            upsert_from_faith_routine,
        )
        upsert_from_faith_routine(instance)
    except Exception as e:
        logger.warning(
            "Failed to project faith routine %s to calendar: %s",
            instance.pk, e,
        )


@receiver(post_delete, sender='faith.UserReadingPlan')
def handle_reading_plan_deleted(sender, instance, **kwargs):
    """When a UserReadingPlan is deleted, remove its calendar events."""
    try:
        from apps.calendar_engine.services.projection import (
            delete_faith_events,
        )
        delete_faith_events(instance)
    except Exception as e:
        logger.warning(
            "Failed to clean up calendar events for faith routine %s: %s",
            instance.pk, e,
        )
