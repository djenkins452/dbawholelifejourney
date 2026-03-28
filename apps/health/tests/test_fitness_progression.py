# ==============================================================================
# File: test_fitness_progression.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for deterministic weight progression service.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-27
# ==============================================================================

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.health.models import (
    Exercise,
    ExerciseSet,
    WorkoutExercise,
    WorkoutSession,
)
from apps.health.services.fitness_progression import get_recommended_weight
from apps.users.models import User


class FitnessProgressionTestCase(TestCase):
    """Base class with helper to create completed workout sessions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@progression.com", password="testpass123"
        )
        self.exercise = Exercise.objects.create(
            name="Bench Press",
            category="resistance",
            movement_type="weighted",
            load_type="external",
            muscle_group="chest",
        )

    def _create_session(self, days_ago, exercise, weight, sets=3, warmup_weight=None):
        """Create a completed workout session with sets at the given weight."""
        now = timezone.now()
        session = WorkoutSession.objects.create(
            user=self.user,
            date=(now - timedelta(days=days_ago)).date(),
            name="Test Workout",
            started_at=now - timedelta(days=days_ago, hours=1),
            completed_at=now - timedelta(days=days_ago),
        )
        we = WorkoutExercise.objects.create(
            session=session, exercise=exercise, order=1
        )
        # Add warmup set if specified
        if warmup_weight is not None:
            ExerciseSet.objects.create(
                workout_exercise=we,
                set_number=1,
                weight=Decimal(str(warmup_weight)),
                reps=10,
                is_warmup=True,
            )
        # Add working sets
        for i in range(sets):
            set_num = (2 if warmup_weight else 1) + i
            ExerciseSet.objects.create(
                workout_exercise=we,
                set_number=set_num,
                weight=Decimal(str(weight)),
                reps=8,
                is_warmup=False,
            )
        return session


class TestPlateauDetection(FitnessProgressionTestCase):
    """Test plateau detection across 3 sessions."""

    def test_identical_weight_3_sessions_triggers_progression(self):
        """3 sessions at 135 lbs → recommend 140 lbs."""
        for days in [7, 5, 2]:
            self._create_session(days, self.exercise, 135)

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertIsNotNone(result)
        self.assertEqual(result["weight"], 140.0)
        self.assertTrue(result["progression"]["applied"])
        self.assertEqual(result["progression"]["increase"], 5.0)
        self.assertEqual(result["progression"]["reason"], "plateau_3_sessions")

    def test_weights_within_tolerance_triggers_progression(self):
        """3 sessions with weights within ±5 lbs → progression based on most recent."""
        self._create_session(7, self.exercise, 135)
        self._create_session(5, self.exercise, 137)
        self._create_session(2, self.exercise, 140)  # most recent

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertTrue(result["progression"]["applied"])
        self.assertEqual(result["weight"], 145.0)  # 140 + 5

    def test_weights_outside_tolerance_no_progression(self):
        """3 sessions with >5 lb spread → no progression."""
        self._create_session(7, self.exercise, 135)
        self._create_session(5, self.exercise, 145)  # 10 lb difference
        self._create_session(2, self.exercise, 140)

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertFalse(result["progression"]["applied"])
        self.assertEqual(result["weight"], 140.0)  # just the most recent
        self.assertEqual(result["progression"]["increase"], 0)

    def test_exact_5lb_spread_triggers_progression(self):
        """Boundary: exactly 5 lb spread should trigger (<=5 check)."""
        self._create_session(7, self.exercise, 135)
        self._create_session(5, self.exercise, 135)
        self._create_session(2, self.exercise, 140)

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertTrue(result["progression"]["applied"])


class TestInsufficientData(FitnessProgressionTestCase):
    """Test behavior with fewer than 3 sessions."""

    def test_two_sessions_no_progression(self):
        """Only 2 sessions → no progression."""
        self._create_session(5, self.exercise, 135)
        self._create_session(2, self.exercise, 135)

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertIsNotNone(result)
        self.assertFalse(result["progression"]["applied"])
        self.assertEqual(result["weight"], 135.0)

    def test_one_session_no_progression(self):
        """Only 1 session → no progression."""
        self._create_session(2, self.exercise, 135)

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertFalse(result["progression"]["applied"])
        self.assertEqual(result["weight"], 135.0)

    def test_no_sessions_returns_none(self):
        """No history at all → None."""
        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertIsNone(result)


class TestWarmupExclusion(FitnessProgressionTestCase):
    """Test that warmup sets are excluded from max weight calculation."""

    def test_warmup_at_higher_weight_ignored(self):
        """Warmup set at 200 lbs should not affect max working weight of 135."""
        for days in [7, 5, 2]:
            self._create_session(days, self.exercise, 135, warmup_weight=200)

        result = get_recommended_weight(self.user, self.exercise.pk)

        # Should still detect plateau at 135, not 200
        self.assertTrue(result["progression"]["applied"])
        self.assertEqual(result["weight"], 140.0)


class TestEdgeCases(FitnessProgressionTestCase):
    """Edge cases and boundary conditions."""

    def test_incomplete_session_excluded(self):
        """Sessions without completed_at are ignored."""
        # 2 completed sessions
        self._create_session(5, self.exercise, 135)
        self._create_session(2, self.exercise, 135)

        # 1 incomplete session (started but not finished)
        now = timezone.now()
        incomplete = WorkoutSession.objects.create(
            user=self.user,
            date=now.date(),
            name="Incomplete",
            started_at=now,
            completed_at=None,
        )
        we = WorkoutExercise.objects.create(
            session=incomplete, exercise=self.exercise, order=1
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, weight=Decimal("135"), reps=8
        )

        result = get_recommended_weight(self.user, self.exercise.pk)

        # Only 2 completed sessions → no progression
        self.assertFalse(result["progression"]["applied"])

    def test_time_based_exercise_returns_none(self):
        """Exercise with no weight data returns None."""
        plank = Exercise.objects.create(
            name="Plank",
            category="resistance",
            movement_type="time",
            load_type="movement",
            muscle_group="core",
        )
        now = timezone.now()
        for days in [7, 5, 2]:
            session = WorkoutSession.objects.create(
                user=self.user,
                date=(now - timedelta(days=days)).date(),
                name="Core",
                started_at=now - timedelta(days=days, hours=1),
                completed_at=now - timedelta(days=days),
            )
            we = WorkoutExercise.objects.create(
                session=session, exercise=plank, order=1
            )
            ExerciseSet.objects.create(
                workout_exercise=we,
                set_number=1,
                weight=None,
                reps=None,
                duration_seconds=60,
            )

        result = get_recommended_weight(self.user, plank.pk)

        self.assertIsNone(result)

    def test_different_users_isolated(self):
        """Progression is per-user — other user's data doesn't leak."""
        other_user = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        # Other user has 3 sessions at 135
        now = timezone.now()
        for days in [7, 5, 2]:
            session = WorkoutSession.objects.create(
                user=other_user,
                date=(now - timedelta(days=days)).date(),
                name="Other",
                started_at=now - timedelta(days=days, hours=1),
                completed_at=now - timedelta(days=days),
            )
            we = WorkoutExercise.objects.create(
                session=session, exercise=self.exercise, order=1
            )
            ExerciseSet.objects.create(
                workout_exercise=we, set_number=1, weight=Decimal("135"), reps=8
            )

        # Our user has no history
        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertIsNone(result)

    def test_max_weight_used_across_mixed_sets(self):
        """When sets have different weights, max is used per session."""
        now = timezone.now()
        for days in [7, 5, 2]:
            session = WorkoutSession.objects.create(
                user=self.user,
                date=(now - timedelta(days=days)).date(),
                name="Mixed",
                started_at=now - timedelta(days=days, hours=1),
                completed_at=now - timedelta(days=days),
            )
            we = WorkoutExercise.objects.create(
                session=session, exercise=self.exercise, order=1
            )
            # Set 1: lighter
            ExerciseSet.objects.create(
                workout_exercise=we, set_number=1, weight=Decimal("115"), reps=10
            )
            # Set 2: heavier (the max)
            ExerciseSet.objects.create(
                workout_exercise=we, set_number=2, weight=Decimal("135"), reps=8
            )
            # Set 3: back down
            ExerciseSet.objects.create(
                workout_exercise=we, set_number=3, weight=Decimal("125"), reps=10
            )

        result = get_recommended_weight(self.user, self.exercise.pk)

        # Max working weight is 135 across all 3 sessions → plateau
        self.assertTrue(result["progression"]["applied"])
        self.assertEqual(result["weight"], 140.0)

    def test_more_than_3_sessions_uses_last_3(self):
        """Only the 3 most recent sessions matter."""
        # Old session at 100 lbs (should be ignored)
        self._create_session(30, self.exercise, 100)
        # Last 3 at 135
        self._create_session(7, self.exercise, 135)
        self._create_session(5, self.exercise, 135)
        self._create_session(2, self.exercise, 135)

        result = get_recommended_weight(self.user, self.exercise.pk)

        self.assertTrue(result["progression"]["applied"])
        self.assertEqual(result["weight"], 140.0)
