# ==============================================================================
# File: apps/purpose/services/goal_queries.py
# Description: Canonical goal query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical goal queries.

Every method returns a QuerySet (not evaluated) so callers can chain.
"""

from apps.purpose.models import LifeGoal


class GoalQueries:
    """Canonical, deterministic goal queries. No instance state."""

    @classmethod
    def active(cls, user):
        """Active life goals."""
        return LifeGoal.objects.filter(user=user, status='active')

    @classmethod
    def with_milestones(cls, user):
        """Active goals prefetched with milestones (avoids N+1)."""
        return cls.active(user).prefetch_related('milestones')

    @classmethod
    def overdue(cls, user, as_of=None):
        """Active goals past their target date."""
        if as_of is None:
            from django.utils import timezone
            as_of = timezone.localdate()
        return cls.active(user).filter(
            target_date__isnull=False,
            target_date__lt=as_of,
        )
