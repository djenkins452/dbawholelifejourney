# ==============================================================================
# File: apps/purpose/services/goal_signal_config.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Goal-signal source configuration and auto-population
# Created: 2026-03-14 (Architecture Evolution Phase 5)
# ==============================================================================
"""
GoalSignalConfigService — Manages GoalSignalSource configuration.

Auto-populates default signal sources when a goal is created, based on
the goal's LifeDomain. Can be customized by the user or CoS.

Part of the WLJ Architecture Evolution — Layer 4 (Goal Momentum).
"""

import logging

from apps.purpose.models import GoalSignalSource

logger = logging.getLogger(__name__)


# Domain → default signal sources with weights (must sum to ~1.0)
DOMAIN_SIGNAL_DEFAULTS = {
    'health': [
        ('health_activity', 0.35),
        ('health_biometrics', 0.25),
        ('medication_adherence', 0.20),
        ('nutrition_compliance', 0.20),
    ],
    'faith': [
        ('faith_practice', 0.50),
        ('mental_reflection', 0.30),
        ('relational_engagement', 0.20),
    ],
    'mind': [
        ('mental_reflection', 0.40),
        ('cognitive_fitness', 0.30),
        ('health_biometrics', 0.15),
        ('faith_practice', 0.15),
    ],
    'work': [
        ('productivity_progress', 0.50),
        ('mental_reflection', 0.20),
        ('health_activity', 0.15),
        ('cognitive_fitness', 0.15),
    ],
    'finance': [
        ('financial_health', 0.60),
        ('productivity_progress', 0.25),
        ('mental_reflection', 0.15),
    ],
    'relationships': [
        ('relational_engagement', 0.50),
        ('mental_reflection', 0.25),
        ('faith_practice', 0.25),
    ],
    'life': [
        ('productivity_progress', 0.40),
        ('health_activity', 0.20),
        ('mental_reflection', 0.20),
        ('faith_practice', 0.20),
    ],
    # Fallback for domains not listed above
    'personal': [
        ('productivity_progress', 0.30),
        ('mental_reflection', 0.30),
        ('health_activity', 0.20),
        ('faith_practice', 0.20),
    ],
}


class GoalSignalConfigService:
    """Manages GoalSignalSource auto-population and retrieval."""

    @staticmethod
    def auto_populate(goal):
        """
        Create default GoalSignalSource records based on goal's domain.

        Only creates if no existing sources exist (idempotent).
        Returns list of created GoalSignalSource records.
        """
        # Don't overwrite existing configuration
        if goal.signal_sources.exists():
            return list(goal.signal_sources.all())

        # Determine domain slug
        domain_slug = ''
        if goal.domain:
            domain_slug = goal.domain.slug

        # Look up defaults
        defaults = DOMAIN_SIGNAL_DEFAULTS.get(
            domain_slug,
            DOMAIN_SIGNAL_DEFAULTS.get('personal'),
        )

        created = []
        for signal_type, weight in defaults:
            source = GoalSignalSource.objects.create(
                goal=goal,
                signal_type=signal_type,
                weight=weight,
            )
            created.append(source)

        logger.info(
            "Auto-populated %d signal sources for goal '%s' (domain=%s)",
            len(created), goal.title, domain_slug,
        )

        return created

    @staticmethod
    def get_signal_weights(goal):
        """
        Return {signal_type: weight} mapping for a goal.

        If no GoalSignalSource records exist, auto-populates first.
        """
        sources = goal.signal_sources.all()
        if not sources.exists():
            sources = GoalSignalConfigService.auto_populate(goal)

        return {s.signal_type: s.weight for s in sources}
