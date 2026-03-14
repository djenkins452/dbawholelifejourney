# ==============================================================================
# File: apps/purpose/signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Signal handlers for Goals, Milestones, and Habits
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-27
# ==============================================================================
"""
Purpose Module Signals

Handles automatic calendar projection when goals, milestones, and habits
are created or updated. Ensures the Time Command Center stays in sync
with all purpose-related items instantly.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='purpose.LifeGoal')
def handle_goal_saved(sender, instance, created, **kwargs):
    """
    When a LifeGoal is saved, project it to the calendar engine.
    Creates/updates DEADLINE_MARKER for the goal's target_date.
    Also projects any milestones with target_dates.
    On creation, auto-populates GoalSignalSource records.
    """
    try:
        from apps.calendar_engine.services.projection import upsert_from_goal
        upsert_from_goal(instance)
    except Exception as e:
        logger.warning(
            "Failed to project goal %s to calendar: %s", instance.pk, e
        )

    # Architecture Evolution Phase 5: auto-populate signal sources on creation
    if created:
        try:
            from apps.purpose.services.goal_signal_config import GoalSignalConfigService
            GoalSignalConfigService.auto_populate(instance)
        except Exception as e:
            logger.warning(
                "Failed to auto-populate signal sources for goal %s: %s",
                instance.pk, e,
            )


@receiver(post_save, sender='purpose.GoalMilestone')
def handle_milestone_saved(sender, instance, **kwargs):
    """
    When a GoalMilestone is saved, project it to the calendar engine.
    Creates/updates DEADLINE_MARKER for the milestone's target_date.
    """
    if not instance.target_date:
        return
    try:
        from apps.calendar_engine.services.projection import _upsert_milestone_marker
        _upsert_milestone_marker(instance.goal, instance)
    except Exception as e:
        logger.warning(
            "Failed to project milestone %s to calendar: %s", instance.pk, e
        )


@receiver(post_save, sender='purpose.HabitGoal')
def handle_habit_saved(sender, instance, **kwargs):
    """
    When a HabitGoal is saved, project it to the calendar engine.
    Creates a recurring CalendarEvent with matching recurrence rule.
    """
    try:
        from apps.calendar_engine.services.projection import upsert_from_habit
        upsert_from_habit(instance)
    except Exception as e:
        logger.warning(
            "Failed to project habit %s to calendar: %s", instance.pk, e
        )


@receiver(post_delete, sender='purpose.LifeGoal')
def handle_goal_deleted(sender, instance, **kwargs):
    """When a LifeGoal is deleted, remove its calendar events."""
    try:
        from apps.calendar_engine.services.projection import delete_goal_events
        delete_goal_events(instance)
    except Exception as e:
        logger.warning(
            "Failed to clean up calendar events for goal %s: %s",
            instance.pk, e
        )


@receiver(post_delete, sender='purpose.HabitGoal')
def handle_habit_deleted(sender, instance, **kwargs):
    """When a HabitGoal is deleted, remove its calendar events."""
    try:
        from apps.calendar_engine.services.projection import delete_habit_events
        delete_habit_events(instance)
    except Exception as e:
        logger.warning(
            "Failed to clean up calendar events for habit %s: %s",
            instance.pk, e
        )
