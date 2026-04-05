# ==============================================================================
# File: apps/dashboard/signals.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Django signals for dashboard cache invalidation
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-06
# ==============================================================================
"""
Dashboard Cache Invalidation Signals

These signals automatically invalidate the relevant dashboard cache sections
when underlying data changes. This ensures users always see fresh data while
still benefiting from caching on repeated page loads.

Signal Strategy:
- Each model change invalidates only its relevant cache section
- Uses post_save and post_delete to catch all changes
- Lazy imports to avoid circular dependencies
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _invalidate_health(user):
    """Helper to invalidate health cache."""
    from .cache import DashboardCacheService
    DashboardCacheService.invalidate_health(user)


# NOTE: SAE refreshes have been consolidated into apps/ai/signals.py
# (the single canonical location for all SAE state updates).
# This file only handles v1 dashboard cache invalidation.


def _invalidate_journal(user):
    """Helper to invalidate journal cache."""
    from .cache import DashboardCacheService
    DashboardCacheService.invalidate_journal(user)


def _invalidate_faith(user):
    """Helper to invalidate faith cache."""
    from .cache import DashboardCacheService
    DashboardCacheService.invalidate_faith(user)


def _invalidate_life(user):
    """Helper to invalidate life cache."""
    from .cache import DashboardCacheService
    DashboardCacheService.invalidate_life(user)


def _invalidate_purpose(user):
    """Helper to invalidate purpose cache."""
    from .cache import DashboardCacheService
    DashboardCacheService.invalidate_purpose(user)


# =============================================================================
# HEALTH SIGNALS
# =============================================================================

@receiver(post_save, sender='health.WeightEntry')
@receiver(post_delete, sender='health.WeightEntry')
def invalidate_on_weight_change(sender, instance, **kwargs):
    """Invalidate health cache when weight entry changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.HeartRateEntry')
@receiver(post_delete, sender='health.HeartRateEntry')
def invalidate_on_heart_rate_change(sender, instance, **kwargs):
    """Invalidate health cache when heart rate entry changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.GlucoseEntry')
@receiver(post_delete, sender='health.GlucoseEntry')
def invalidate_on_glucose_change(sender, instance, **kwargs):
    """Invalidate health cache when glucose entry changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.Intake')
@receiver(post_delete, sender='health.Intake')
def invalidate_on_medicine_change(sender, instance, **kwargs):
    """Invalidate health cache when medicine changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.IntakeLog')
@receiver(post_delete, sender='health.IntakeLog')
def invalidate_on_medicine_log_change(sender, instance, **kwargs):
    """Invalidate health cache when medicine log changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.IntakeSchedule')
@receiver(post_delete, sender='health.IntakeSchedule')
def invalidate_on_medicine_schedule_change(sender, instance, **kwargs):
    """Invalidate health cache when medicine schedule changes."""
    _invalidate_health(instance.medicine.user)


@receiver(post_save, sender='health.WorkoutSession')
@receiver(post_delete, sender='health.WorkoutSession')
def invalidate_on_workout_change(sender, instance, **kwargs):
    """Invalidate health cache when workout changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.PersonalRecord')
@receiver(post_delete, sender='health.PersonalRecord')
def invalidate_on_pr_change(sender, instance, **kwargs):
    """Invalidate health cache when personal record changes."""
    _invalidate_health(instance.user)


@receiver(post_save, sender='health.HealthProfile')
def invalidate_on_health_profile_change(sender, instance, **kwargs):
    """Invalidate health cache when health profile changes (weight goal, etc)."""
    _invalidate_health(instance.user)


# =============================================================================
# JOURNAL SIGNALS
# =============================================================================

@receiver(post_save, sender='journal.JournalEntry')
@receiver(post_delete, sender='journal.JournalEntry')
def invalidate_on_journal_change(sender, instance, **kwargs):
    """Invalidate journal cache when entry changes."""
    _invalidate_journal(instance.user)


# =============================================================================
# FAITH SIGNALS
# =============================================================================

@receiver(post_save, sender='faith.PrayerRequest')
@receiver(post_delete, sender='faith.PrayerRequest')
def invalidate_on_prayer_change(sender, instance, **kwargs):
    """Invalidate faith cache when prayer changes."""
    _invalidate_faith(instance.user)


@receiver(post_save, sender='faith.SavedVerse')
@receiver(post_delete, sender='faith.SavedVerse')
def invalidate_on_verse_change(sender, instance, **kwargs):
    """Invalidate faith cache when saved verse changes."""
    _invalidate_faith(instance.user)


@receiver(post_save, sender='health.FastingWindow')
@receiver(post_delete, sender='health.FastingWindow')
def invalidate_on_fasting_change(sender, instance, **kwargs):
    """Invalidate health cache when fasting entry changes."""
    _invalidate_health(instance.user)


# =============================================================================
# LIFE SIGNALS
# =============================================================================

@receiver(post_save, sender='life.Task')
@receiver(post_delete, sender='life.Task')
def invalidate_on_task_change(sender, instance, **kwargs):
    """Invalidate life cache when task changes."""
    _invalidate_life(instance.user)


@receiver(post_save, sender='life.LifeEvent')
@receiver(post_delete, sender='life.LifeEvent')
def invalidate_on_event_change(sender, instance, **kwargs):
    """Invalidate life cache when event changes."""
    _invalidate_life(instance.user)


@receiver(post_save, sender='life.Project')
@receiver(post_delete, sender='life.Project')
def invalidate_on_project_change(sender, instance, **kwargs):
    """Invalidate life cache when project changes."""
    _invalidate_life(instance.user)


# =============================================================================
# PURPOSE SIGNALS
# =============================================================================

@receiver(post_save, sender='purpose.LifeGoal')
@receiver(post_delete, sender='purpose.LifeGoal')
def invalidate_on_goal_change(sender, instance, **kwargs):
    """Invalidate purpose cache when goal changes."""
    _invalidate_purpose(instance.user)


@receiver(post_save, sender='purpose.GoalMilestone')
@receiver(post_delete, sender='purpose.GoalMilestone')
def invalidate_on_milestone_change(sender, instance, **kwargs):
    """Invalidate purpose cache when milestone changes."""
    _invalidate_purpose(instance.goal.user)
