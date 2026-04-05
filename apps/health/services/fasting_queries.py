# ==============================================================================
# File: apps/health/services/fasting_queries.py
# Description: Canonical fasting query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical fasting queries.

COMPLETION RULE:
  A fast is "completed" when ended_at is set and status='active'.
  An open fast (ended_at is null) is "in progress".
"""

from apps.health.models import FastingWindow


class FastingQueries:
    """Canonical, deterministic fasting queries. No instance state."""

    @classmethod
    def current_active(cls, user):
        """Currently active (open) fasting window, or None."""
        return FastingWindow.objects.filter(
            user=user, ended_at__isnull=True, status='active',
        ).order_by('-started_at').first()

    @classmethod
    def is_fasting(cls, user):
        """Boolean: is user currently fasting?"""
        return FastingWindow.objects.filter(
            user=user, ended_at__isnull=True, status='active',
        ).exists()

    @classmethod
    def completed_in_range(cls, user, start_dt, end_dt):
        """Completed fasts started in a datetime range."""
        return FastingWindow.objects.filter(
            user=user,
            ended_at__isnull=False,
            started_at__gte=start_dt,
            status='active',
        )

    @classmethod
    def last_completed(cls, user):
        """Most recent completed fast, or None."""
        return FastingWindow.objects.filter(
            user=user, ended_at__isnull=False, status='active',
        ).order_by('-ended_at').first()
