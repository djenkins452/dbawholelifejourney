"""Tests for the workout → routine auto-complete qualification gate.

The gate in apps/health/signals.py::handle_workout_session_completed (Block 2)
must qualify a day's workouts for routine auto-complete when EITHER:
  (a) any completed session has logged workout_exercises, OR
  (b) total completed duration >= WORKOUT_COMPLETION_THRESHOLD_MINUTES.

Regression case: a structured strength session (16 sets, 10,550 lbs) logged
with duration_minutes = 0 must still mark the "Workout" routine complete.
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.health.models import (
    Exercise,
    ExerciseSet,
    WorkoutExercise,
    WorkoutSession,
)
from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.users.models import TermsAcceptance, User


class _Base(TestCase):
    """Shared setup: user + a Morning Routine with a 'Workout' schedule item."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="bridge-gate@test.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.routine = Routine.objects.create(
            user=self.user, name="Morning Routine",
            time_of_day="morning", is_active=True,
        )
        self.workout_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Workout",
            scheduled_time=time(6, 0),
            grace_period_minutes=60,
            days_of_week="0,1,2,3,4,5,6",
            is_active=True,
        )

        # Shared exercise fixture — resistance, external load.
        self.exercise = Exercise.objects.create(
            name="Bench Press", category="resistance",
            movement_type="weighted", load_type="external",
        )

    def _today(self):
        return timezone.localdate()

    def _make_session(self, *, duration_minutes=None, completed=True,
                       session_mode="structured"):
        now = timezone.now()
        started = now - timedelta(minutes=30)
        return WorkoutSession.objects.create(
            user=self.user,
            date=self._today(),
            name="Test Session",
            duration_minutes=duration_minutes,
            started_at=started,
            completed_at=now if completed else None,
            session_mode=session_mode,
            source="manual",
        )

    def _routine_logged(self):
        return RoutineLog.objects.filter(
            user=self.user,
            schedule=self.workout_schedule,
            scheduled_date=self._today(),
            completion_source="workout",
        ).exists()


class StructuredSessionQualifiesOnExercises(_Base):
    """A structured session with 0 duration but logged exercises MUST qualify."""

    def test_zero_duration_with_one_set_completes_routine(self):
        """Regression: 0-duration structured session with 1 set triggers routine complete."""
        session = self._make_session(duration_minutes=0)
        we = WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=0,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, reps=10, weight=135,
        )
        # Re-save to retrigger the post_save signal now that sets exist.
        session.save()

        self.assertTrue(
            self._routine_logged(),
            "Structured session with logged exercises must mark the "
            "'Workout' routine complete even with 0 duration_minutes",
        )

    def test_null_duration_with_two_sets_still_completes_routine(self):
        """Early-stage exercises (1-2 sets) must count too."""
        session = self._make_session(duration_minutes=None)
        we = WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=0,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, reps=8, weight=95,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=2, reps=8, weight=95,
        )
        session.save()

        self.assertTrue(self._routine_logged())

    def test_exercise_row_without_sets_still_qualifies(self):
        """Presence of any WorkoutExercise row qualifies — the gate is
        'exercises logged', not 'sets logged'. Sets may be added later."""
        session = self._make_session(duration_minutes=0)
        WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=0,
        )
        session.save()

        self.assertTrue(self._routine_logged())


class ActivitySessionStillRequiresDuration(_Base):
    """Activity-mode sessions with no exercises still gated by duration."""

    def test_short_activity_without_exercises_does_not_qualify(self):
        """A 5-minute activity-mode session (e.g. brief walk, no exercises)
        must NOT mark the routine complete — preserves the original
        guardrail against routine completion by trivial movement."""
        self._make_session(
            duration_minutes=5, session_mode="activity",
        )

        self.assertFalse(
            self._routine_logged(),
            "5-minute activity session with no exercises must not "
            "auto-complete the workout routine",
        )

    def test_long_activity_without_exercises_qualifies(self):
        """A 30-minute activity-mode session (pickleball, run) qualifies
        via the duration branch — no exercises required."""
        self._make_session(
            duration_minutes=30, session_mode="activity",
        )

        self.assertTrue(self._routine_logged())


class UncompletedSessionIgnored(_Base):
    """Incomplete sessions must not qualify, regardless of exercises."""

    def test_in_progress_structured_session_does_not_complete_routine(self):
        session = self._make_session(duration_minutes=0, completed=False)
        we = WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=0,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, reps=10, weight=135,
        )
        session.save()

        self.assertFalse(
            self._routine_logged(),
            "Session without completed_at must not qualify even with sets",
        )
