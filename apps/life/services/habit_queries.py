# ==============================================================================
# File: apps/life/services/habit_queries.py
# Description: Canonical habit query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical habit queries.
"""

from apps.purpose.models import HabitGoal


class HabitQueries:
    """Canonical, deterministic habit queries. No instance state."""

    @classmethod
    def active(cls, user):
        """Active habit goals."""
        return HabitGoal.objects.filter(user=user, status='active')

    @classmethod
    def active_count(cls, user):
        """Count of active habits."""
        return cls.active(user).count()
