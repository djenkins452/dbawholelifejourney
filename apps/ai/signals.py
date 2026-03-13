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


def invalidate_daily_insight_cache(user):
    """Directly invalidate the daily dashboard insight so it regenerates on next load."""
    from .dashboard_ai import DashboardAI
    DashboardAI.invalidate_daily_insight(user)


def invalidate_state_snapshot(user):
    """
    Delete today's UserStateSnapshot so the AI assessment regenerates on next load.

    Called when any user data changes (journal, health, tasks, faith, etc.)
    so the assistant dashboard always shows up-to-date information.
    """
    from apps.core.utils import get_user_today
    from .models import UserStateSnapshot
    try:
        today = get_user_today(user)
        deleted, _ = UserStateSnapshot.objects.filter(user=user, snapshot_date=today).delete()
        if deleted:
            logger.debug(f"Invalidated state snapshot for user {user.id}")
    except Exception:
        pass  # Don't let snapshot invalidation break data saves


def _refresh_sae_module(user, module):
    """
    Refresh a single SAE module so UserState stays fresh.

    Called from post_save/post_delete signals to keep SAE in sync with
    data changes that happen outside Beth's action pipeline (web forms,
    API endpoints, recurring task processing, etc.).

    This uses the existing update_user_state() which:
    - Respects Learning Mode gate (no writes during calibration)
    - Calls only the affected module's builder (not a full rebuild)
    - Reads-modifies-writes UserState.state_data
    """
    try:
        from apps.core.ai_state.state_updater import update_user_state
        update_user_state(user, module)
    except Exception:
        # SAE refresh must never break data saves
        logger.debug("SAE refresh failed for module '%s', user %s", module, user.id, exc_info=True)


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
    # Also directly invalidate the daily insight cache
    invalidate_daily_insight_cache(instance.user)
    # Also invalidate personal data cache for journal and mood
    invalidate_personal_data_cache(instance.user, 'journal')
    if instance.mood:
        invalidate_personal_data_cache(instance.user, 'mood')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'journal')


@receiver(post_delete, sender='journal.JournalEntry')
def invalidate_insights_on_journal_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a journal entry is deleted."""
    insight_types = ['daily_insight', 'weekly_summary', 'journal_home']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache for journal and mood
    invalidate_personal_data_cache(instance.user, 'journal')
    if instance.mood:
        invalidate_personal_data_cache(instance.user, 'mood')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'journal')


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
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'goals')


@receiver(post_delete, sender='purpose.LifeGoal')
def invalidate_insights_on_goal_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a goal is deleted."""
    insight_types = ['daily_insight', 'goal_progress', 'purpose_home']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'goals')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'goals')


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
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


@receiver(post_delete, sender='health.GlucoseEntry')
def invalidate_insights_on_glucose_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when blood glucose is deleted."""
    insight_types = ['daily_insight', 'glucose_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'glucose')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


@receiver(post_save, sender='health.WeightEntry')
def invalidate_insights_on_weight_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when weight is saved."""
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'weight')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')

    # Derive lean_mass and fat_mass from weight + body_fat_percentage
    if instance.value and instance.value > 0 and instance.body_fat_percentage is not None:
        try:
            from apps.health.services.body_composition_service import sync_derived_body_composition
            sync_derived_body_composition(instance.user, instance)
        except Exception:
            logger.error("Failed to sync derived body composition", exc_info=True)


@receiver(post_delete, sender='health.WeightEntry')
def invalidate_insights_on_weight_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when weight is deleted."""
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'weight')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


@receiver(post_save, sender='health.BodyCompositionEntry')
def invalidate_state_on_body_comp_save(sender, instance, created, **kwargs):
    """Invalidate SAE state when body composition data changes."""
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


@receiver(post_delete, sender='health.BodyCompositionEntry')
def invalidate_state_on_body_comp_delete(sender, instance, **kwargs):
    """Invalidate SAE state when body composition data is deleted."""
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


# =============================================================================
# LIFE/TASKS SIGNALS
# =============================================================================

@receiver(post_save, sender='life.Task')
def invalidate_insights_on_task_save(sender, instance, created, **kwargs):
    """Invalidate relevant insights when a task is saved."""
    insight_types = ['daily_insight', 'life_home', 'accountability_nudge']
    invalidate_user_insights(instance.user, insight_types)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'tasks')


@receiver(post_delete, sender='life.Task')
def invalidate_insights_on_task_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a task is deleted."""
    insight_types = ['daily_insight', 'life_home']
    invalidate_user_insights(instance.user, insight_types)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'tasks')


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
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_delete, sender='faith.PrayerRequest')
def invalidate_insights_on_prayer_delete(sender, instance, **kwargs):
    """Invalidate relevant insights when a prayer request is deleted."""
    insight_types = ['daily_insight', 'faith_home', 'prayer_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    # Also invalidate personal data cache
    invalidate_personal_data_cache(instance.user, 'faith')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_save, sender='faith.SavedVerse')
def invalidate_cache_on_saved_verse_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a saved verse is saved."""
    invalidate_personal_data_cache(instance.user, 'faith')
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_delete, sender='faith.SavedVerse')
def invalidate_cache_on_saved_verse_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a saved verse is deleted."""
    invalidate_personal_data_cache(instance.user, 'faith')
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_save, sender='faith.FaithMilestone')
def invalidate_cache_on_faith_milestone_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a faith milestone is saved."""
    invalidate_personal_data_cache(instance.user, 'faith')
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_delete, sender='faith.FaithMilestone')
def invalidate_cache_on_faith_milestone_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a faith milestone is deleted."""
    invalidate_personal_data_cache(instance.user, 'faith')
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_save, sender='faith.UserReadingPlan')
def invalidate_cache_on_reading_plan_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a reading plan is saved."""
    invalidate_personal_data_cache(instance.user, 'faith')
    _refresh_sae_module(instance.user, 'faith')


@receiver(post_delete, sender='faith.UserReadingPlan')
def invalidate_cache_on_reading_plan_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a reading plan is deleted."""
    invalidate_personal_data_cache(instance.user, 'faith')
    _refresh_sae_module(instance.user, 'faith')


# =============================================================================
# MEDICATION SIGNALS
# =============================================================================

@receiver(post_save, sender='health.MedicineLog')
def invalidate_cache_on_medicine_log_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a medicine log is saved."""
    invalidate_personal_data_cache(instance.user, 'medication')
    invalidate_daily_insight_cache(instance.user)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')
    _refresh_sae_module(instance.user, 'medicine')


@receiver(post_delete, sender='health.MedicineLog')
def invalidate_cache_on_medicine_log_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a medicine log is deleted."""
    invalidate_personal_data_cache(instance.user, 'medication')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')
    _refresh_sae_module(instance.user, 'medicine')


# =============================================================================
# FOOD SIGNALS
# =============================================================================

@receiver(post_save, sender='health.FoodEntry')
def invalidate_cache_on_food_entry_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a food entry is saved."""
    invalidate_personal_data_cache(instance.user, 'food')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'nutrition')


@receiver(post_delete, sender='health.FoodEntry')
def invalidate_cache_on_food_entry_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a food entry is deleted."""
    invalidate_personal_data_cache(instance.user, 'food')
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'nutrition')


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
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


@receiver(post_delete, sender='health.WaterEntry')
def invalidate_cache_on_water_entry_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a water entry is deleted."""
    invalidate_personal_data_cache(instance.user, 'water')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


# =============================================================================
# WORKOUT/FITNESS SIGNALS
# =============================================================================

@receiver(post_save, sender='health.WorkoutSession')
def invalidate_cache_on_workout_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when a workout session is saved."""
    invalidate_personal_data_cache(instance.user, 'workout')
    invalidate_daily_insight_cache(instance.user)
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'fitness')


@receiver(post_delete, sender='health.WorkoutSession')
def invalidate_cache_on_workout_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when a workout session is deleted."""
    invalidate_personal_data_cache(instance.user, 'workout')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'fitness')


@receiver(post_save, sender='health.ExerciseSet')
def invalidate_cache_on_exercise_set_save(sender, instance, created, **kwargs):
    """Invalidate personal data cache when an exercise set is saved."""
    # ExerciseSet -> workout_exercise -> session -> user
    if instance.workout_exercise and instance.workout_exercise.session:
        user = instance.workout_exercise.session.user
        if user:
            invalidate_personal_data_cache(user, 'workout')


@receiver(post_save, sender='health.ExerciseSet')
def auto_detect_pr_on_exercise_set_create(sender, instance, created, **kwargs):
    """Automatically detect personal records when a new exercise set is created."""
    if not created:
        return
    try:
        from apps.health.pr_utils import check_and_record_pr
        check_and_record_pr(instance)
    except Exception:
        logger.error("Error in automatic PR detection", exc_info=True)


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
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')


@receiver(post_delete, sender='health.StepsEntry')
def invalidate_cache_on_steps_delete(sender, instance, **kwargs):
    """Invalidate personal data cache when steps are deleted."""
    invalidate_personal_data_cache(instance.user, 'workout')
    # Also invalidate health insights
    insight_types = ['daily_insight', 'health_home', 'health_encouragement']
    invalidate_user_insights(instance.user, insight_types)
    invalidate_state_snapshot(instance.user)
    _refresh_sae_module(instance.user, 'health')
