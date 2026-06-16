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
        """Distinct PLAN completion dates in reverse order.

        Plan-only. For canonical faith history (days-since / streak) use
        ``bible_completion_dates`` instead — it also folds in the
        routine→faith bridge so it cannot diverge from execution truth.
        """
        return list(
            UserReadingProgress.objects.filter(
                user_plan__user=user, is_completed=True,
                completed_at__isnull=False,
            ).values_list(
                'completed_at__date', flat=True,
            ).distinct().order_by('-completed_at__date')[:limit]
        )

    @classmethod
    def _routine_bible_completed_on(cls, user, target_date):
        """True if a routine→faith-bridge Bible item was completed on a date."""
        try:
            from apps.core.execution.execution_truth_engine import (
                FAITH_BIBLE_NAMES,
            )
            from apps.life.models import RoutineLog
            names = RoutineLog.objects.filter(
                user=user, scheduled_date=target_date,
                log_status__in=[
                    RoutineLog.STATUS_COMPLETED, RoutineLog.STATUS_COMPLETED_LATE],
            ).values_list('schedule__name', flat=True)
            return any(
                n and n.strip().lower() in FAITH_BIBLE_NAMES for n in names)
        except Exception:
            return False

    @classmethod
    def is_bible_complete_on(cls, user, target_date):
        """CANONICAL per-date Bible-reading completion across BOTH sources
        (reading plan + routine→faith bridge). Every consumer that needs
        "was Bible reading done on date X?" must use this so they cannot
        diverge from execution truth / the dashboard (trust contract 2026-06-16)."""
        return (
            cls.has_reading_on(user, target_date)
            or cls._routine_bible_completed_on(user, target_date)
        )

    @classmethod
    def bible_completion_dates(cls, user, limit=90):
        """THE single canonical set of dates Bible reading was completed.

        Unions BOTH canonical sources that execution_truth_engine counts:
          1. reading-plan progress (UserReadingProgress.is_completed)
          2. the routine→faith bridge — a completed routine item named like
             "Bible Reading" (FAITH_BIBLE_NAMES)

        This exists so faith history metrics (days-since, streak) derive from
        the SAME truth as the dashboard / adherence / routine engine and can
        never diverge (the "22 days since scripture while reading daily via a
        routine" trust bug, 2026-06-16). Returns dates newest-first. Never
        raises (routine source is best-effort).
        """
        from datetime import timedelta

        from django.utils import timezone

        dates = set(cls.reading_completion_dates(user, limit=limit))
        try:
            from apps.core.execution.execution_truth_engine import (
                FAITH_BIBLE_NAMES,
            )
            from apps.life.models import RoutineLog

            cutoff = timezone.now().date() - timedelta(days=limit)
            rows = RoutineLog.objects.filter(
                user=user,
                scheduled_date__gte=cutoff,
                log_status__in=[
                    RoutineLog.STATUS_COMPLETED,
                    RoutineLog.STATUS_COMPLETED_LATE,
                ],
            ).values_list('schedule__name', 'scheduled_date')
            for name, d in rows:
                if d and name and name.strip().lower() in FAITH_BIBLE_NAMES:
                    dates.add(d)
        except Exception:
            pass  # routine bridge best-effort; plan dates still returned
        return sorted((d for d in dates if d), reverse=True)[:limit]

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
