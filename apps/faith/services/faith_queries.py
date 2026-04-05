# ==============================================================================
# File: apps/faith/services/faith_queries.py
# Description: Canonical faith domain query service. All consumers (execution
#              truth, SAE state builder, CoS context, views) MUST use these
#              methods instead of ad-hoc PrayerRequest/UserReadingPlan QuerySets.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical faith queries.

Every method returns a QuerySet (not evaluated) so callers can chain
additional filters, slice, or aggregate as needed.

COMPLETION RULES:
  Bible reading completed = UserReadingProgress with is_completed=True
  Prayer completed = faith-module Task with completion_status='completed'
  These may also be satisfied by routine bridges (see execution_truth_engine).
"""

from apps.faith.models import PrayerRequest, UserReadingPlan, UserReadingProgress


class FaithQueries:
    """Canonical, deterministic faith queries. No instance state."""

    # ── Reading Plans ────────────────────────────────────────────

    @classmethod
    def active_reading_plans(cls, user):
        """Active Bible reading plans."""
        return UserReadingPlan.objects.filter(
            user=user, plan_status='active',
        ).exclude(status='deleted')

    @classmethod
    def has_active_plan(cls, user):
        """Boolean: does user have an active reading plan?"""
        return cls.active_reading_plans(user).exists()

    @classmethod
    def reading_completed_on(cls, user, target_date):
        """Reading progress entries completed on a specific date."""
        active_plans = cls.active_reading_plans(user)
        return UserReadingProgress.objects.filter(
            user_plan__in=active_plans,
            is_completed=True,
            completed_at__date=target_date,
        )

    @classmethod
    def has_reading_on(cls, user, target_date):
        """Boolean: did user complete reading on this date?"""
        return cls.reading_completed_on(user, target_date).exists()

    @classmethod
    def last_reading(cls, user):
        """Most recent completed reading progress entry (or None)."""
        return UserReadingProgress.objects.filter(
            user_plan__user=user, is_completed=True,
        ).order_by('-completed_at').first()

    @classmethod
    def reading_completion_dates(cls, user, limit=60):
        """Distinct completion dates in reverse order (for streak calc)."""
        return list(
            UserReadingProgress.objects.filter(
                user_plan__user=user, is_completed=True,
                completed_at__isnull=False,
            ).values_list(
                'completed_at__date', flat=True,
            ).distinct().order_by('-completed_at__date')[:limit]
        )

    # ── Prayer Requests ──────────────────────────────────────────

    @classmethod
    def unanswered_prayers(cls, user):
        """Active, unanswered prayer requests."""
        return PrayerRequest.objects.filter(user=user, is_answered=False)

    @classmethod
    def answered_prayers(cls, user):
        """Answered prayer requests."""
        return PrayerRequest.objects.filter(user=user, is_answered=True)

    @classmethod
    def urgent_prayers(cls, user):
        """Unanswered prayer requests marked as urgent."""
        return cls.unanswered_prayers(user).filter(priority='urgent')

    # ── Faith Tasks ──────────────────────────────────────────────

    @classmethod
    def faith_task_completed_on(cls, user, target_date):
        """Faith-module tasks completed on a specific date."""
        from apps.life.models import Task
        return Task.objects.filter(
            user=user,
            module='faith',
            completion_status='completed',
            completed_at__date=target_date,
        )

    @classmethod
    def has_faith_task_completed_on(cls, user, target_date):
        """Boolean: did user complete a faith task on this date?"""
        return cls.faith_task_completed_on(user, target_date).exists()
