"""
Dashboard V2 signal handlers for cache invalidation.

Listens to model save/delete signals to invalidate relevant cache sections.
Follows the same pattern as apps/dashboard/signals.py.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import DashboardV2CacheService

logger = logging.getLogger(__name__)


def _invalidate_for_user(user_id, sections):
    """Invalidate specific dashboard_v2 cache sections for a user."""
    for section in sections:
        DashboardV2CacheService.invalidate(user_id, section)


# ── Health signals ──────────────────────────────────────────────────


def _health_signal_handler(sender, instance, **kwargs):
    if hasattr(instance, "user_id"):
        _invalidate_for_user(instance.user_id, ["momentum", "daily_prog", "state", "execution"])


def _connect_health_signals():
    """Connect health model signals. Called at app ready time."""
    try:
        from apps.health.models import (
            GlucoseEntry,
            HeartRateEntry,
            Medicine,
            MedicineLog,
            MedicineSchedule,
            PersonalRecord,
            WeightEntry,
            WorkoutSession,
        )

        for model in [
            WeightEntry, HeartRateEntry, GlucoseEntry,
            Medicine, MedicineLog, MedicineSchedule,
            WorkoutSession, PersonalRecord,
        ]:
            post_save.connect(_health_signal_handler, sender=model, weak=False)
            post_delete.connect(_health_signal_handler, sender=model, weak=False)
    except ImportError:
        logger.debug("Health models not available for dashboard_v2 signals")


# ── Purpose signals (goals, habits) ────────────────────────────────


def _purpose_signal_handler(sender, instance, **kwargs):
    if hasattr(instance, "user_id"):
        _invalidate_for_user(instance.user_id, ["momentum", "daily_prog"])


def _connect_purpose_signals():
    try:
        from apps.purpose.models import GoalMilestone, HabitGoal, LifeGoal

        for model in [LifeGoal, GoalMilestone, HabitGoal]:
            post_save.connect(_purpose_signal_handler, sender=model, weak=False)
            post_delete.connect(_purpose_signal_handler, sender=model, weak=False)
    except ImportError:
        logger.debug("Purpose models not available for dashboard_v2 signals")


# ── Life signals (tasks) ───────────────────────────────────────────


def _life_signal_handler(sender, instance, **kwargs):
    if hasattr(instance, "user_id"):
        _invalidate_for_user(instance.user_id, ["momentum", "daily_prog", "execution"])


def _connect_life_signals():
    try:
        from apps.life.models import Task

        post_save.connect(_life_signal_handler, sender=Task, weak=False)
        post_delete.connect(_life_signal_handler, sender=Task, weak=False)
    except ImportError:
        logger.debug("Life models not available for dashboard_v2 signals")


# ── Journal signals ────────────────────────────────────────────────


def _journal_signal_handler(sender, instance, **kwargs):
    if hasattr(instance, "user_id"):
        _invalidate_for_user(instance.user_id, ["momentum", "daily_prog"])


def _connect_journal_signals():
    try:
        from apps.journal.models import JournalEntry

        post_save.connect(_journal_signal_handler, sender=JournalEntry, weak=False)
        post_delete.connect(_journal_signal_handler, sender=JournalEntry, weak=False)
    except ImportError:
        logger.debug("Journal models not available for dashboard_v2 signals")


# ── Faith signals ──────────────────────────────────────────────────


def _faith_signal_handler(sender, instance, **kwargs):
    if hasattr(instance, "user_id"):
        _invalidate_for_user(instance.user_id, ["momentum", "daily_prog"])


def _connect_faith_signals():
    try:
        from apps.faith.models import PrayerRequest, SavedVerse

        for model in [PrayerRequest, SavedVerse]:
            post_save.connect(_faith_signal_handler, sender=model, weak=False)
            post_delete.connect(_faith_signal_handler, sender=model, weak=False)
    except ImportError:
        logger.debug("Faith models not available for dashboard_v2 signals")


# ── Connect all on import ──────────────────────────────────────────

_connect_health_signals()
_connect_purpose_signals()
_connect_life_signals()
_connect_journal_signals()
_connect_faith_signals()
