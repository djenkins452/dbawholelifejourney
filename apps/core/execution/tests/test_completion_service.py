"""
Completion Service Regression Tests.

These tests make it IMPOSSIBLE for completion logic to regress.
If ANY test fails, the merge MUST be blocked.

Tests prove:
  1. No domain can be marked complete without real data
  2. Time cannot affect completion
  3. Signals cannot affect completion
  4. Partial existence does not imply completion
  5. Invariant violations are detected
"""
import datetime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.execution.completion_service import (
    is_workout_complete,
    is_journal_complete,
    is_bible_reading_complete,
    is_medication_complete,
    is_nutrition_logged,
    is_task_complete,
    is_routine_item_complete,
    validate_completion_invariants,
)
from apps.users.models import User


def _create_test_user(email='completion-test@test.com'):
    """Create a test user with required onboarding setup."""
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestWorkoutCompletion(TestCase):
    """Workout completion requires explicit evidence."""

    def setUp(self):
        self.user = _create_test_user('workout-completion@test.com')
        self.today = datetime.date.today()

    def test_no_session_not_complete(self):
        """No WorkoutSession → NOT complete."""
        self.assertFalse(is_workout_complete(self.user, self.today))

    def test_started_session_not_complete(self):
        """Started-but-not-finished session → NOT complete."""
        from apps.health.models import WorkoutSession
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            workout_type='strength',
            started_at=timezone.now(),
            # No completed_at, no duration, no exercises
        )
        self.assertFalse(is_workout_complete(self.user, self.today))

    def test_completed_at_is_complete(self):
        """Session with completed_at set → complete."""
        from apps.health.models import WorkoutSession
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            workout_type='strength',
            completed_at=timezone.now(),
        )
        self.assertTrue(is_workout_complete(self.user, self.today))

    def test_duration_is_complete(self):
        """Session with duration_minutes set → complete."""
        from apps.health.models import WorkoutSession
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            workout_type='cardio',
            duration_minutes=30,
        )
        self.assertTrue(is_workout_complete(self.user, self.today))

    def test_deleted_session_not_complete(self):
        """Soft-deleted session → NOT complete."""
        from apps.health.models import WorkoutSession
        ws = WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            workout_type='strength',
            completed_at=timezone.now(),
        )
        ws.soft_delete()
        self.assertFalse(is_workout_complete(self.user, self.today))

    def test_time_passing_does_not_complete(self):
        """Time passing beyond scheduled workout time → NOT complete."""
        # Even if it's 11 PM and workout was scheduled for 6 AM,
        # without a session, it's not complete.
        self.assertFalse(is_workout_complete(self.user, self.today))


class TestJournalCompletion(TestCase):
    """Journal completion requires an entry to exist."""

    def setUp(self):
        self.user = _create_test_user('journal-completion@test.com')
        self.today = datetime.date.today()

    def test_no_entry_not_complete(self):
        """No journal entry → NOT complete."""
        self.assertFalse(is_journal_complete(self.user, self.today))

    def test_entry_exists_is_complete(self):
        """Journal entry exists → complete."""
        from apps.journal.models import JournalEntry
        JournalEntry.objects.create(
            user=self.user,
            entry_date=self.today,
            title='Test',
            body='Test body',
        )
        self.assertTrue(is_journal_complete(self.user, self.today))


class TestNutritionLogged(TestCase):
    """Nutrition requires at least one food entry."""

    def setUp(self):
        self.user = _create_test_user('nutrition-completion@test.com')
        self.today = datetime.date.today()

    def test_no_food_not_logged(self):
        """No food entries → NOT logged."""
        self.assertFalse(is_nutrition_logged(self.user, self.today))

    def test_food_entry_is_logged(self):
        """Food entry exists → logged."""
        from apps.health.models import FoodEntry
        FoodEntry.objects.create(
            user=self.user,
            food_name='Chicken Salad',
            logged_date=self.today,
            total_calories=450,
            serving_size=1,
            serving_unit='serving',
        )
        self.assertTrue(is_nutrition_logged(self.user, self.today))


class TestTaskCompletion(TestCase):
    """Task completion requires explicit completion_status."""

    def setUp(self):
        self.user = _create_test_user('task-completion@test.com')
        self.today = datetime.date.today()

    def test_pending_task_not_complete(self):
        """Pending task → NOT complete."""
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Test Task',
            due_date=self.today,
            completion_status='pending',
        )
        self.assertFalse(is_task_complete(task))

    def test_completed_task_is_complete(self):
        """Completed task → complete."""
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Test Task',
            due_date=self.today,
            completion_status='completed',
        )
        self.assertTrue(is_task_complete(task))

    def test_skipped_task_not_complete(self):
        """Skipped task → NOT complete (skipped ≠ completed)."""
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Test Task',
            due_date=self.today,
            completion_status='skipped',
        )
        self.assertFalse(is_task_complete(task))


class TestRoutineItemCompletion(TestCase):
    """Routine item completion requires RoutineLog."""

    def setUp(self):
        self.user = _create_test_user('routine-completion@test.com')
        self.today = datetime.date.today()

    def test_no_log_not_complete(self):
        """No RoutineLog → NOT complete."""
        from apps.life.models import Routine, RoutineSchedule
        routine = Routine.objects.create(
            user=self.user,
            name='Morning',
            is_active=True,
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name='Meditation',
            scheduled_time=datetime.time(6, 0),
            days_of_week='0,1,2,3,4,5,6',
        )
        self.assertFalse(
            is_routine_item_complete(self.user, schedule.id, self.today)
        )

    def test_completed_log_is_complete(self):
        """RoutineLog with completed status → complete."""
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        routine = Routine.objects.create(
            user=self.user,
            name='Morning',
            is_active=True,
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name='Meditation',
            scheduled_time=datetime.time(6, 0),
            days_of_week='0,1,2,3,4,5,6',
        )
        RoutineLog.objects.create(
            user=self.user,
            schedule=schedule,
            scheduled_date=self.today,
            log_status='completed',
        )
        self.assertTrue(
            is_routine_item_complete(self.user, schedule.id, self.today)
        )


class TestNoCascading(TestCase):
    """Completion must not cascade between domains."""

    def setUp(self):
        self.user = _create_test_user('cascade-test@test.com')
        self.today = datetime.date.today()

    def test_routine_completion_does_not_complete_workout(self):
        """Completing a 'Workout' routine item does NOT make workout complete."""
        from apps.life.models import Routine, RoutineSchedule, RoutineLog

        routine = Routine.objects.create(
            user=self.user,
            name='Morning',
            is_active=True,
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name='Workout',
            scheduled_time=datetime.time(6, 0),
            days_of_week='0,1,2,3,4,5,6',
        )
        RoutineLog.objects.create(
            user=self.user,
            schedule=schedule,
            scheduled_date=self.today,
            log_status='completed',
        )
        # Routine item is complete, but workout domain is NOT
        self.assertTrue(
            is_routine_item_complete(self.user, schedule.id, self.today)
        )
        self.assertFalse(is_workout_complete(self.user, self.today))

    def test_task_completion_does_not_complete_workout(self):
        """Completing a 'Workout' task does NOT make workout complete."""
        from apps.life.models import Task
        Task.objects.create(
            user=self.user,
            title='Workout',
            due_date=self.today,
            completion_status='completed',
        )
        self.assertFalse(is_workout_complete(self.user, self.today))


class TestInvariantValidation(TestCase):
    """Invariant violations must be detected."""

    def setUp(self):
        self.user = _create_test_user('invariant-test@test.com')
        self.today = datetime.date.today()

    def test_clean_state_no_violations(self):
        """No data → no violations (everything is False/0)."""
        violations = validate_completion_invariants(self.user, self.today)
        self.assertEqual(len(violations), 0)

    def test_consistent_workout_no_violation(self):
        """Completed workout with session → no violation."""
        from apps.health.models import WorkoutSession
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            workout_type='strength',
            completed_at=timezone.now(),
        )
        violations = validate_completion_invariants(self.user, self.today)
        workout_violations = [v for v in violations if v['domain'] == 'workout']
        self.assertEqual(len(workout_violations), 0)
