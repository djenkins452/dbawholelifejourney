# ==============================================================================
# File: apps/ai/signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Django signals for AI insight cache invalidation
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# Last Updated: 2026-01-04
# ==============================================================================
"""
AI Signals - Invalidate cached insights when user data changes.

These signals ensure that AI insights are refreshed when relevant data
is created, updated, or deleted. The invalidation respects the refresh_frequency
configuration on each AIPromptConfig.

Signal Handlers:
    - invalidate_insights_on_journal_change: Invalidates insights when journal entries change
    - invalidate_insights_on_goal_change: Invalidates insights when goals change
    - invalidate_insights_on_health_change: Invalidates insights when health data changes
    - invalidate_insights_on_task_change: Invalidates insights when tasks change
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def invalidate_user_insights(user, insight_types=None):
    """
    Invalidate cached AI insights for a user.

    Args:
        user: The user whose insights should be invalidated
        insight_types: List of insight types to invalidate. If None, invalidates all.
    """
    from .models import AIInsight, AIPromptConfig

    # Get configs that should refresh on data change
    configs = AIPromptConfig.objects.filter(is_active=True)
    types_to_invalidate = []

    for config in configs:
        if config.should_refresh_on_data_change():
            if insight_types is None or config.prompt_type in insight_types:
                types_to_invalidate.append(config.prompt_type)

    if types_to_invalidate:
        # Delete cached insights for these types
        deleted_count, _ = AIInsight.objects.filter(
            user=user,
            insight_type__in=types_to_invalidate
        ).delete()

        if deleted_count > 0:
            logger.debug(
                f"Invalidated {deleted_count} AI insights for user {user.id}: {types_to_invalidate}"
            )


# =============================================================================
# JOURNAL SIGNALS
# =============================================================================

@receiver(post_save, sender='journal.JournalEntry')
def invalidate_insights_on_journal_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a journal entry is saved."""
    insight_types = ['daily_insight', 'weekly_summary', 'journal_home', 'journal_reflection']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='journal.JournalEntry')
def invalidate_insights_on_journal_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a journal entry is deleted."""
    insight_types = ['daily_insight', 'weekly_summary', 'journal_home']
    invalidate_user_insights(instance.user, insight_types)


# =============================================================================
# PURPOSE/GOALS SIGNALS
# =============================================================================

@receiver(post_save, sender='purpose.LifeGoal')
def invalidate_insights_on_goal_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a goal is saved."""
    insight_types = ['daily_insight', 'goal_progress', 'purpose_home']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='purpose.LifeGoal')
def invalidate_insights_on_goal_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a goal is deleted."""
    insight_types = ['daily_insight', 'goal_progress', 'purpose_home']
    invalidate_user_insights(instance.user, insight_types)


# =============================================================================
# HEALTH SIGNALS
# =============================================================================

@receiver(post_save, sender='health.GlucoseEntry')
def invalidate_insights_on_glucose_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when blood glucose is saved."""
    insight_types = ['daily_insight', 'glucose_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='health.GlucoseEntry')
def invalidate_insights_on_glucose_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when blood glucose is deleted."""
    insight_types = ['daily_insight', 'glucose_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_save, sender='health.WeightEntry')
def invalidate_insights_on_weight_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when weight is saved."""
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='health.WeightEntry')
def invalidate_insights_on_weight_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when weight is deleted."""
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


# =============================================================================
# LIFE/TASKS SIGNALS
# =============================================================================

@receiver(post_save, sender='life.Task')
def invalidate_insights_on_task_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a task is saved."""
    insight_types = ['daily_insight', 'life_home', 'accountability_nudge']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='life.Task')
def invalidate_insights_on_task_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a task is deleted."""
    insight_types = ['daily_insight', 'life_home']
    invalidate_user_insights(instance.user, insight_types)


# =============================================================================
# FAITH SIGNALS
# =============================================================================

@receiver(post_save, sender='faith.PrayerRequest')
def invalidate_insights_on_prayer_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a prayer request is saved."""
    insight_types = ['daily_insight', 'faith_home', 'prayer_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='faith.PrayerRequest')
def invalidate_insights_on_prayer_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a prayer request is deleted."""
    insight_types = ['daily_insight', 'faith_home', 'prayer_encouragement']
    invalidate_user_insights(instance.user, insight_types)
