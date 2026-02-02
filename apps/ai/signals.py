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


def invalidate_personal_data_cache(user, data_type):
    """
    Invalidate cached personal data for a user and data type.

    This is called when user creates/updates/deletes log entries to ensure
    the assistant service returns fresh data.

    Args:
        user: The user whose data cache should be invalidated
        data_type: The type of data to invalidate (weight, journal, medication, food, mood)
    """
    from assistant.data_service import invalidate_user_data_cache
    invalidate_user_data_cache(user.id, data_type)
    logger.debug(f"Invalidated personal data cache for user {user.id}: {data_type}")


# =============================================================================
# JOURNAL SIGNALS
# =============================================================================

@receiver(post_save, sender='journal.JournalEntry')
def invalidate_insights_on_journal_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a journal entry is saved."""
    insight_types = ['daily_insight', 'weekly_summary', 'journal_home', 'journal_reflection']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache for journal and mood
    invalidate_personal_data_cache(instance.user, 'journal')
    if instance.mood:
        invalidate_personal_data_cache(instance.user, 'mood')


@receiver(post_delete, sender='journal.JournalEntry')
def invalidate_insights_on_journal_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a journal entry is deleted."""
    insight_types = ['daily_insight', 'weekly_summary', 'journal_home']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache for journal and mood
    invalidate_personal_data_cache(instance.user, 'journal')
    if instance.mood:
        invalidate_personal_data_cache(instance.user, 'mood')


# =============================================================================
# PURPOSE/GOALS SIGNALS
# =============================================================================

@receiver(post_save, sender='purpose.LifeGoal')
def invalidate_insights_on_goal_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a goal is saved."""
    insight_types = ['daily_insight', 'goal_progress', 'purpose_home']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'goals')


@receiver(post_delete, sender='purpose.LifeGoal')
def invalidate_insights_on_goal_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a goal is deleted."""
    insight_types = ['daily_insight', 'goal_progress', 'purpose_home']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'goals')


# =============================================================================
# HEALTH SIGNALS
# =============================================================================

@receiver(post_save, sender='health.GlucoseEntry')
def invalidate_insights_on_glucose_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when blood glucose is saved."""
    insight_types = ['daily_insight', 'glucose_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'glucose')


@receiver(post_delete, sender='health.GlucoseEntry')
def invalidate_insights_on_glucose_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when blood glucose is deleted."""
    insight_types = ['daily_insight', 'glucose_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'glucose')


@receiver(post_save, sender='health.WeightEntry')
def invalidate_insights_on_weight_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when weight is saved."""
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'weight')


@receiver(post_delete, sender='health.WeightEntry')
def invalidate_insights_on_weight_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when weight is deleted."""
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'weight')


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
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_delete, sender='faith.PrayerRequest')
def invalidate_insights_on_prayer_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a prayer request is deleted."""
    insight_types = ['daily_insight', 'faith_home', 'prayer_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_save, sender='faith.SavedVerse')
def invalidate_cache_on_saved_verse_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a saved verse is saved."""
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_delete, sender='faith.SavedVerse')
def invalidate_cache_on_saved_verse_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a saved verse is deleted."""
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_save, sender='faith.FaithMilestone')
def invalidate_cache_on_faith_milestone_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a faith milestone is saved."""
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_delete, sender='faith.FaithMilestone')
def invalidate_cache_on_faith_milestone_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a faith milestone is deleted."""
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_save, sender='faith.UserReadingPlan')
def invalidate_cache_on_reading_plan_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a reading plan is saved."""
    invalidate_personal_data_cache(instance.user, 'faith')


@receiver(post_delete, sender='faith.UserReadingPlan')
def invalidate_cache_on_reading_plan_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a reading plan is deleted."""
    invalidate_personal_data_cache(instance.user, 'faith')


# =============================================================================
# MEDICATION SIGNALS
# =============================================================================

@receiver(post_save, sender='health.MedicineLog')
def invalidate_cache_on_medicine_log_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a medicine log is saved."""
    invalidate_personal_data_cache(instance.user, 'medication')


@receiver(post_delete, sender='health.MedicineLog')
def invalidate_cache_on_medicine_log_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a medicine log is deleted."""
    invalidate_personal_data_cache(instance.user, 'medication')


# =============================================================================
# FOOD SIGNALS
# =============================================================================

@receiver(post_save, sender='health.FoodEntry')
def invalidate_cache_on_food_entry_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a food entry is saved."""
    invalidate_personal_data_cache(instance.user, 'food')


@receiver(post_delete, sender='health.FoodEntry')
def invalidate_cache_on_food_entry_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a food entry is deleted."""
    invalidate_personal_data_cache(instance.user, 'food')


# =============================================================================
# WATER SIGNALS
# =============================================================================

@receiver(post_save, sender='health.WaterEntry')
def invalidate_cache_on_water_entry_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a water entry is saved."""
    invalidate_personal_data_cache(instance.user, 'water')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='health.WaterEntry')
def invalidate_cache_on_water_entry_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a water entry is deleted."""
    invalidate_personal_data_cache(instance.user, 'water')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


# =============================================================================
# WORKOUT/FITNESS SIGNALS
# =============================================================================

@receiver(post_save, sender='health.WorkoutSession')
def invalidate_cache_on_workout_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a workout session is saved."""
    invalidate_personal_data_cache(instance.user, 'workout')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='health.WorkoutSession')
def invalidate_cache_on_workout_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a workout session is deleted."""
    invalidate_personal_data_cache(instance.user, 'workout')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_save, sender='health.ExerciseSet')
def invalidate_cache_on_exercise_set_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when an exercise set is saved."""
    # ExerciseSet -> workout_exercise -> session -> user
    if instance.workout_exercise and instance.workout_exercise.session:
        user = instance.workout_exercise.session.user
        if user:
            invalidate_personal_data_cache(user, 'workout')


@receiver(post_delete, sender='health.ExerciseSet')
def invalidate_cache_on_exercise_set_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when an exercise set is deleted."""
    # ExerciseSet -> workout_exercise -> session -> user
    if instance.workout_exercise and instance.workout_exercise.session:
        user = instance.workout_exercise.session.user
        if user:
            invalidate_personal_data_cache(user, 'workout')


@receiver(post_save, sender='health.StepsEntry')
def invalidate_cache_on_steps_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when steps are saved."""
    invalidate_personal_data_cache(instance.user, 'workout')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)


@receiver(post_delete, sender='health.StepsEntry')
def invalidate_cache_on_steps_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when steps are deleted."""
    invalidate_personal_data_cache(instance.user, 'workout')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
