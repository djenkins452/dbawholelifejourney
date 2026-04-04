# ==============================================================================
# File: apps/health/tests/test_workout_queries.py
# Description: Regression tests for WorkoutQueries contract — ensures
#              canonical workout completion checks are consistent across
#              execution truth, SAE, and UI.
# ==============================================================================
"""
Tests for WorkoutQueries — the canonical workout completion check.

The key regression case is Bug #1: a started-but-not-completed session
must NOT be reported as "completed". This caused CoS to tell users
"workout completed today" when the Health UI showed no completed workout.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.health.models import WorkoutSession
from apps.health.services.workout_queries import WorkoutQueries


class WorkoutQueriesTestMixin:
    """Shared setup for workout query tests."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            email='wqtest@example.com', password='testpass123',
        )
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)


class TestIsCompletedOn(WorkoutQueriesTestMixin, TestCase):
    """Tests for is_completed_on — the main completion boolean."""

    def test_no_session_returns_false(self):
        self.assertFalse(WorkoutQueries.is_completed_on(self.user, self.today))

    def test_started_not_completed_returns_false(self):
        """REGRESSION: Bug #1 — started but not finished must NOT be completed."""
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            name='Morning Workout',
            started_at=timezone.now(),
            completed_at=None,
        )
        self.assertFalse(WorkoutQueries.is_completed_on(self.user, self.today))

    def test_completed_session_returns_true(self):
        now = timezone.now()
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            name='Morning Workout',
            started_at=now - timedelta(hours=1),
            completed_at=now,
        )
        self.assertTrue(WorkoutQueries.is_completed_on(self.user, self.today))

    def test_deleted_session_excluded(self):
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            completed_at=timezone.now(),
            status='deleted',
        )
        self.assertFalse(WorkoutQueries.is_completed_on(self.user, self.today))

    def test_different_date_not_counted(self):
        WorkoutSession.objects.create(
            user=self.user,
            date=self.yesterday,
            completed_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(WorkoutQueries.is_completed_on(self.user, self.today))


class TestOnDate(WorkoutQueriesTestMixin, TestCase):
    """Tests for on_date — includes in-progress sessions."""

    def test_started_session_included(self):
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            started_at=timezone.now(),
            completed_at=None,
        )
        self.assertTrue(WorkoutQueries.on_date(self.user, self.today).exists())

    def test_deleted_session_excluded(self):
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            started_at=timezone.now(),
            status='deleted',
        )
        self.assertFalse(WorkoutQueries.on_date(self.user, self.today).exists())


class TestCompletedInRange(WorkoutQueriesTestMixin, TestCase):
    """Tests for completed_in_range — analytics/frequency counting."""

    def test_counts_only_completed(self):
        now = timezone.now()
        # 1 completed
        WorkoutSession.objects.create(
            user=self.user, date=self.today,
            completed_at=now,
        )
        # 1 in-progress (should NOT count)
        WorkoutSession.objects.create(
            user=self.user, date=self.yesterday,
            started_at=now - timedelta(days=1),
            completed_at=None,
        )
        qs = WorkoutQueries.completed_in_range(
            self.user, self.yesterday, self.today,
        )
        self.assertEqual(qs.count(), 1)

    def test_range_boundaries_inclusive(self):
        now = timezone.now()
        start = self.today - timedelta(days=7)
        WorkoutSession.objects.create(
            user=self.user, date=start, completed_at=now,
        )
        WorkoutSession.objects.create(
            user=self.user, date=self.today, completed_at=now,
        )
        qs = WorkoutQueries.completed_in_range(self.user, start, self.today)
        self.assertEqual(qs.count(), 2)


class TestExecutionTruthAlignment(WorkoutQueriesTestMixin, TestCase):
    """Verify execution truth engine uses WorkoutQueries correctly."""

    def test_execution_truth_uses_completed_at(self):
        """Execution truth must NOT report in-progress as completed."""
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            started_at=timezone.now(),
            completed_at=None,
        )
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(self.user, self.today)
        self.assertFalse(truth['domains']['workout']['completed'])

    def test_execution_truth_completed_session(self):
        """Execution truth must report completed session correctly."""
        now = timezone.now()
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            started_at=now - timedelta(hours=1),
            completed_at=now,
        )
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(self.user, self.today)
        self.assertTrue(truth['domains']['workout']['completed'])
