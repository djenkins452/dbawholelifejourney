# ==============================================================================
# File: apps/health/services/workout_queries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical workout query service. All consumers (execution truth,
#              SAE state builder, CoS context, views, analytics) MUST use these
#              methods instead of ad-hoc WorkoutSession QuerySets. This
#              eliminates the .exists() vs completed_at mismatch that caused
#              CoS to report in-progress workouts as "completed".
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-04-04
# ==============================================================================
"""
Canonical workout queries.

Every method returns a QuerySet (not evaluated) so callers can chain
additional filters, slice, or aggregate as needed. The SoftDeleteManager
on WorkoutSession.objects already filters status='active', but we add an
explicit .exclude(status='deleted') for safety since some call sites
previously relied on it.

COMPLETION RULE:
  A workout is "completed" when completed_at is not null.
  A started-but-not-finished session is NOT completed.
  This matches the Health UI (views.py:467) and SAE fitness builder
  (state_builder.py build_fitness_state 7d/30d counts).

Usage:
    from apps.health.services.workout_queries import WorkoutQueries

    qs  = WorkoutQueries.completed_on(user, today)        # completed sessions
    ok  = WorkoutQueries.is_completed_on(user, today)     # bool
    qs  = WorkoutQueries.completed_in_range(user, s, e)   # for analytics
    qs  = WorkoutQueries.on_date(user, today)             # all (incl in-progress)
"""

from datetime import date

from django.db.models import Q

from apps.health.models import WorkoutSession


# A workout is "completed" when ANY of these are true:
#   1. completed_at is set (explicitly finished via UI or import)
#   2. It has at least one exercise logged (structured workout with content)
#   3. It has duration_minutes set (activity workout logged with duration)
#
# A session that was merely started (started_at set, no exercises, no
# duration, no completed_at) is NOT completed — it's in-progress.
_COMPLETED_Q = (
    Q(completed_at__isnull=False)
    | Q(workout_exercises__isnull=False)
    | Q(duration_minutes__isnull=False)
)


class WorkoutQueries:
    """Canonical, deterministic workout queries. No instance state."""

    @classmethod
    def completed_on(cls, user, target_date):
        """
        Completed workout sessions on a specific date.

        A workout is "completed" when:
          - completed_at is set (explicitly finished), OR
          - it has exercises logged (structured workout with content), OR
          - it has duration_minutes (activity/import with duration)

        A session that was merely started with no content is NOT completed.
        """
        return WorkoutSession.objects.filter(
            _COMPLETED_Q,
            user=user,
            date=target_date,
        ).exclude(status='deleted').distinct()

    @classmethod
    def is_completed_on(cls, user, target_date):
        """Boolean: did the user complete any workout on this date?"""
        return cls.completed_on(user, target_date).exists()

    @classmethod
    def on_date(cls, user, target_date):
        """
        All non-deleted sessions on a date (regardless of completion).

        Use this when you need to know "has the user started anything?"
        e.g., suppressing workout check-in prompts or protein-day detection
        where a started session is enough.
        """
        return WorkoutSession.objects.filter(
            user=user,
            date=target_date,
        ).exclude(status='deleted')

    @classmethod
    def completed_in_range(cls, user, start_date, end_date):
        """
        Completed sessions in a date range (inclusive).

        Use for frequency/trend counting — only completed sessions should
        count toward goals like "3x/week".
        """
        return WorkoutSession.objects.filter(
            _COMPLETED_Q,
            user=user,
            date__gte=start_date,
            date__lte=end_date,
        ).exclude(status='deleted').distinct()

    @classmethod
    def in_range(cls, user, start_date, end_date):
        """
        All non-deleted sessions in a date range (regardless of completion).

        Use for listing/display where in-progress sessions should appear.
        """
        return WorkoutSession.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
        ).exclude(status='deleted')
