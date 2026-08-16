# ==============================================================================
# File: apps/health/tests/test_fitness_exposure.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fitness Domain Certification (Phase 3f) exposures — training-volume history
#   (reuses the canonical WorkoutSession.total_volume), workout_by_volume ranking, and
#   Personal-Record entity/analysis exposure. Verifies reuse (no re-derived formula),
#   missing≠zero, canonical values, and inherited platform capabilities.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class FitnessExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="fit@test.com", password="x")
        from apps.health.models import Exercise
        cls.bench = Exercise.objects.create(
            name="Bench Press", category="resistance", movement_type="weighted",
            load_type="external", muscle_group="chest")

    def _workout(self, days_ago, sets):
        """Create a completed workout `days_ago` with resistance `sets` = [(weight, reps), …]."""
        from apps.core.utils import get_user_today
        from apps.health.models import WorkoutSession, WorkoutExercise, ExerciseSet
        d = get_user_today(self.user) - timedelta(days=days_ago)
        s = WorkoutSession.objects.create(user=self.user, date=d, name="Push Day",
                                          duration_minutes=60, session_mode="structured")
        we = WorkoutExercise.objects.create(session=s, exercise=self.bench, order=1)
        for i, (w, r) in enumerate(sets, start=1):
            ExerciseSet.objects.create(workout_exercise=we, set_number=i,
                                       weight=Decimal(str(w)), reps=r)
        return s

    def _pr(self, days_ago, weight, reps, pr_type="weight"):
        from apps.core.utils import get_user_today
        from apps.health.models import PersonalRecord
        d = get_user_today(self.user) - timedelta(days=days_ago)
        return PersonalRecord.objects.create(
            user=self.user, exercise=self.bench,
            weight=(None if weight is None else Decimal(str(weight))), reps=reps,
            achieved_date=d, pr_type=pr_type, status="active")

    # --- training_volume history (reuses canonical total_volume; no re-derived formula) ---
    def test_volume_history_sums_canonical_total_volume(self):
        from apps.health.services.workout_history import WorkoutHistory
        # day -2: 100×10 + 100×8 = 1800 ; day -1: 135×5 = 675
        w2 = self._workout(2, [(100, 10), (100, 8)])
        w1 = self._workout(1, [(135, 5)])
        s = WorkoutHistory.volume(self.user, period="last_7_days")
        self.assertEqual(s.unit, "lb")
        self.assertEqual([p.value for p in s.points], [1800.0, 675.0])
        # the per-day value equals the canonical session property (no shadow calc)
        self.assertEqual(s.points[0].value, float(w2.total_volume))
        self.assertEqual(s.points[1].value, float(w1.total_volume))

    def test_volume_history_registered_and_trend_inherited(self):
        from apps.ai.cos_services.domain_history import (
            get_domain_history, history_capability_index)
        self.assertIn("training_volume", history_capability_index().get("health", ()))
        for i, vol in enumerate([(50, 10), (60, 10), (70, 10), (80, 10)]):  # rising volume
            self._workout(4 - i, [vol])
        env = get_domain_history(self.user, "health", "training_volume", period="last_7_days")
        self.assertTrue(env["present"])
        self.assertEqual(env["unit"], "lb")
        self.assertEqual(env["change"]["direction"], "rising")   # Trend inherited

    def test_volume_missing_days_absent_not_zero(self):
        from apps.health.services.workout_history import WorkoutHistory
        self._workout(3, [(100, 10)])       # only one workout day in the window
        s = WorkoutHistory.volume(self.user, period="last_7_days")
        self.assertEqual(s.count(), 1)      # the non-workout days are ABSENT, not 0
        self.assertEqual([p.value for p in s.points], [1000.0])

    # --- workout_by_volume ranking (reuses ranked_entity; canonical value, no recompute) ---
    def test_workout_by_volume_ranks_sessions(self):
        from apps.ai.cos_services.domain_ranked_entity import (
            get_domain_ranked_entity, ranked_entity_capability_index)
        self.assertIn("workout_by_volume",
                      ranked_entity_capability_index().get("health", ()))
        self._workout(2, [(100, 10)])                 # 1000
        self._workout(1, [(100, 10), (100, 10)])      # 2000 (heaviest)
        r = get_domain_ranked_entity(self.user, "workout_by_volume", period="last 7 days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["unit"], "lb")
        self.assertEqual(r["results"][0]["value"], 2000.0)   # heaviest session first
        self.assertEqual(r["results"][1]["value"], 1000.0)
        # The ranked result carries the workout's REAL exercises, so "which exercises had
        # the most volume" is grounded — never a generic squat/deadlift substitution.
        top = r["results"][0]
        names = {x.get("name") for x in top["meta"].get("exercises", [])}
        self.assertIn("Bench Press", names)

    # --- Personal Records exposure (entity + analysis) ---
    def test_personal_records_entity_and_e1rm(self):
        from apps.health.services.pr_queries import PersonalRecordQueries
        self._pr(5, 225, 3)
        ents = PersonalRecordQueries.describe(self.user)
        self.assertEqual(len(ents), 1)
        e = ents[0]
        self.assertEqual(e.kind, "personal_record")
        self.assertIn("Bench Press", e.identity)
        self.assertEqual(e.performance["weight_lb"], 225.0)
        self.assertIsNotNone(e.performance["estimated_1rm_lb"])   # Brzycki, canonical prop

    def test_personal_records_soft_delete_respected(self):
        from apps.health.services.pr_queries import PersonalRecordQueries
        p = self._pr(3, 200, 5)
        p.status = "deleted"
        p.save(update_fields=["status"])
        self.assertEqual(PersonalRecordQueries.describe(self.user), [])

    def test_personal_records_analysis_subject_holds_data(self):
        from apps.ai.cos_services.domain_analysis import (
            analysis_capability_index, get_domain_analysis)
        self.assertIn("personal_records",
                      analysis_capability_index().get("health", ()))
        self._pr(4, 315, 1)
        env = get_domain_analysis(self.user, "health", "personal_records")
        self.assertEqual(env["status"], "ready")
        self.assertTrue(env["holds_data"])

    def test_personal_records_empty_is_honest(self):
        from apps.ai.cos_services.domain_analysis import get_domain_analysis
        env = get_domain_analysis(self.user, "health", "personal_records")
        self.assertEqual(env["status"], "empty")
        self.assertFalse(env["holds_data"])
