# ==============================================================================
# File: apps/health/tests/test_workout_history_count.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression — WorkoutHistory.sessions counts SESSIONS, not
#   (sessions × exercises). completed_in_range's _COMPLETED_Q LEFT-JOINs
#   workout_exercises, so a plain Count("id") over the .values("date").annotate()
#   GROUP BY inflated the total by exercises-per-session (4 workouts of 7
#   exercises → "28 workout sessions"). Must use Count(distinct=True).
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.models import (
    Exercise, ExerciseSet, WorkoutExercise, WorkoutSession,
)
from apps.health.services.workout_history import WorkoutHistory
from apps.ai.cos_services.domain_history import get_domain_history

User = get_user_model()


def _workout_with_exercises(user, when, n_exercises):
    s = WorkoutSession.objects.create(user=user, date=when, name=f"W-{when}")
    for i in range(n_exercises):
        ex = Exercise.objects.create(name=f"Ex-{when}-{i}", category="resistance",
                                     load_type="external", is_active=True)
        we = WorkoutExercise.objects.create(session=s, exercise=ex, order=i)
        ExerciseSet.objects.create(workout_exercise=we, set_number=1,
                                   weight=Decimal("100"), reps=10)
    return s


class WorkoutSessionCountRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="whc@test.com", password="x")
        today = date.today()
        # 4 completed workouts in the last 7 days, 7 exercises each (the 28-bug shape)
        for d in (1, 2, 4, 6):
            _workout_with_exercises(cls.user, today - timedelta(days=d), 7)

    def test_provider_counts_sessions_not_exercises(self):
        series = WorkoutHistory.sessions(self.user, "last_7_days")
        d = series.to_dict()
        # 4 sessions — NOT 28 (4 × 7 exercises)
        self.assertEqual(d["total"], 4)
        self.assertEqual(d["unit"], "sessions")
        # every day with a workout counts exactly one session
        self.assertTrue(all(p["value"] == 1 for p in d["points"]))

    def test_history_surface_reports_four_sessions(self):
        r = get_domain_history(self.user, "health", "workouts", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["unit"], "sessions")

    def test_single_multi_exercise_workout_is_one_session(self):
        u = User.objects.create_user(email="one@test.com", password="x")
        _workout_with_exercises(u, date.today(), 10)   # one workout, ten exercises
        r = get_domain_history(u, "health", "workouts", period="last_7_days")
        self.assertEqual(r["total"], 1)                # one session, not ten
