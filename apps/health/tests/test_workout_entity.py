# ==============================================================================
# File: apps/health/tests/test_workout_entity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Health Entity provider — WorkoutSession participates in the Truth
#   Resolution Layer's Entity surface (DomainTruth.describe → get_entity) as a
#   CompleteEntity, answering "what exercises did I do", "did I do calf raises",
#   "what weight/sets/volume", "summarize my workout" from deterministic truth.
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.models import (
    Exercise, ExerciseSet, WorkoutExercise, WorkoutSession,
)
from apps.health.services.health_domain_truth import HealthDomainTruth
from apps.ai.cos_services.domain_entity import (
    get_domain_entity, entity_capability_index,
)

User = get_user_model()


def _exercise(name, category="resistance", load_type="external"):
    return Exercise.objects.create(
        name=name, category=category, load_type=load_type, is_active=True,
    )


def _logged(session, exercise, order, sets):
    we = WorkoutExercise.objects.create(session=session, exercise=exercise, order=order)
    for i, (w, reps) in enumerate(sets, start=1):
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=i,
            weight=Decimal(str(w)) if w is not None else None, reps=reps,
        )
    return we


class WorkoutEntityProviderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="we@test.com", password="x")
        # Yesterday's completed "Leg Day": Calf Raise + Squat
        s = WorkoutSession.objects.create(
            user=cls.user, date=date.today() - timedelta(days=1), name="Leg Day",
        )
        _logged(s, _exercise("Calf Raise"), 0, [(45, 12), (45, 12), (45, 12)])
        _logged(s, _exercise("Squat"), 1, [(135, 10), (135, 10), (135, 10)])
        cls.session = s

    def _leg_day(self):
        ents = HealthDomainTruth(self.user).describe("workout")
        return next(e for e in ents if e.identity.startswith("Leg Day"))

    # --- the core deterministic retrieval ---
    def test_describe_returns_workout_complete_entities(self):
        ents = HealthDomainTruth(self.user).describe("workout")
        self.assertTrue(ents)
        e = self._leg_day()
        self.assertEqual(e.kind, "workout")
        self.assertEqual(e.status, "completed")

    # --- "what exercises did I do?" / "did I do calf raises?" ---
    def test_exercise_names_answer_did_i_do_calf_raises(self):
        e = self._leg_day()
        names = {x["name"] for x in e.definition["exercises"]}
        self.assertIn("Calf Raise", names)
        self.assertIn("Squat", names)
        self.assertEqual(e.definition["exercise_count"], 2)

    # --- "what weight / what sets did I complete?" (per-set detail) ---
    def test_per_set_weight_and_reps_present(self):
        e = self._leg_day()
        detail = {d["name"]: d for d in e.extensions["exercise_detail"]}
        calf_sets = detail["Calf Raise"]["sets"]
        self.assertEqual(len(calf_sets), 3)
        self.assertEqual(calf_sets[0]["weight_lb"], 45.0)
        self.assertEqual(calf_sets[0]["reps"], 12)

    # --- "what was my workout volume?" (reuses canonical set.volume) ---
    def test_strength_load_matches_canonical_volume(self):
        e = self._leg_day()
        # Calf 45x12x3 = 1620 ; Squat 135x10x3 = 4050 ; total 5670
        self.assertEqual(e.performance["strength_load_lb"], 5670.0)
        self.assertEqual(e.performance["total_sets"], 6)

    # --- record-level truth is composed, never raw rows ---
    def test_no_raw_row_fields(self):
        e = self._leg_day()
        self.assertNotIn("user_id", e.definition)
        self.assertNotIn("id", e.definition)

    # --- describe_one by workout name ---
    def test_describe_one_by_name(self):
        e = HealthDomainTruth(self.user).describe_one("Leg")
        self.assertIsNotNone(e)
        self.assertTrue(e.identity.startswith("Leg Day"))
        self.assertIsNone(HealthDomainTruth(self.user).describe_one("Nonexistent"))

    # --- an activity workout (no exercises) still describes itself ---
    def test_activity_workout_describes(self):
        WorkoutSession.objects.create(
            user=self.user, date=date.today(), name="Morning Run",
            session_mode="activity", workout_type="Running",
            duration_minutes=32, distance_miles=Decimal("3.10"),
        )
        ents = HealthDomainTruth(self.user).describe("workout")
        run = next(e for e in ents if e.identity.startswith("Morning Run"))
        self.assertEqual(run.definition["exercises"], [])
        self.assertEqual(run.performance["duration_minutes"], 32)
        self.assertEqual(run.performance["distance_miles"], 3.1)

    def test_unknown_entity_type_raises(self):
        with self.assertRaises(KeyError):
            HealthDomainTruth(self.user).describe("nutrition_log")


class WorkoutEntitySurfaceWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="wes@test.com", password="x")
        s = WorkoutSession.objects.create(
            user=cls.user, date=date.today(), name="Pull Day",
        )
        _logged(s, _exercise("Pull Up", load_type="bodyweight"), 0, [(0, 8)])

    # --- health now participates in the Entity capability catalog ---
    def test_health_participates_in_entity_catalog(self):
        idx = entity_capability_index()
        self.assertIn("health", idx)
        self.assertIn("workout", idx["health"])

    # --- end-to-end through the Model Interface entity read surface ---
    def test_get_entity_resolves_workouts(self):
        r = get_domain_entity(self.user, "health", entity_type="workout")
        self.assertEqual(r["status"], "ready")
        self.assertGreaterEqual(r["count"], 1)
        names = {x["name"]
                 for e in r["entities"]
                 for x in e["definition"]["exercises"]}
        self.assertIn("Pull Up", names)

    # --- honest empty for a user with no workouts (never "I couldn't find") ---
    def test_empty_for_user_without_workouts(self):
        fresh = User.objects.create_user(email="nowork@test.com", password="x")
        r = get_domain_entity(fresh, "health", entity_type="workout")
        self.assertEqual(r["status"], "empty")
        self.assertEqual(r["count"], 0)
