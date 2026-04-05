# ==============================================================================
# File: apps/health/services/nutrition_queries.py
# Description: Canonical nutrition/food query service.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical nutrition queries.
"""

from apps.health.models import FoodEntry


class NutritionQueries:
    """Canonical, deterministic nutrition queries. No instance state."""

    @classmethod
    def entries_on_date(cls, user, target_date):
        """Active food entries logged on a specific date."""
        return FoodEntry.objects.filter(
            user=user, logged_date=target_date, status='active',
        )

    @classmethod
    def has_logged_on(cls, user, target_date):
        """Boolean: did user log food on this date?"""
        return cls.entries_on_date(user, target_date).exists()

    @classmethod
    def entries_in_range(cls, user, start_date, end_date):
        """Active food entries in a date range (inclusive)."""
        return FoodEntry.objects.filter(
            user=user,
            logged_date__gte=start_date,
            logged_date__lte=end_date,
            status='active',
        )

    @classmethod
    def last_entry(cls, user):
        """Most recent active food entry date, or None."""
        return FoodEntry.objects.filter(
            user=user, status='active',
        ).order_by('-logged_date', '-logged_time').first()
