# ==============================================================================
# File: apps/ai/tests/test_truth_surface_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Truth-surface SELECTION contract. History (aggregate/period) and
#   Entity (individual-record detail) must be semantically distinct in the tool
#   schemas, the capability index, and the returned envelopes, so the model
#   reliably picks the right surface (the workout "7 sessions" vs "calf raises"
#   defect). No live-model assertions — pure deterministic contract + integration.
# ==============================================================================
import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface.constitution import truth_tools
from apps.ai.cos_services.current_context import _capabilities
from apps.ai.cos_services.domain_history import get_domain_history, history_capability_index
from apps.ai.cos_services.domain_entity import get_domain_entity, entity_capability_index

User = get_user_model()


def _desc(name):
    tool = next(t for t in truth_tools() if t["function"]["name"] == name)
    return tool["function"]["description"].lower()


def _workout(user, when, name, exercises):
    from apps.health.models import (
        Exercise, ExerciseSet, WorkoutExercise, WorkoutSession,
    )
    s = WorkoutSession.objects.create(user=user, date=when, name=name)
    for order, (ename, sets) in enumerate(exercises):
        ex = Exercise.objects.create(name=ename, category="resistance",
                                     load_type="external", is_active=True)
        we = WorkoutExercise.objects.create(session=s, exercise=ex, order=order)
        for i, (w, reps) in enumerate(sets, 1):
            ExerciseSet.objects.create(workout_exercise=we, set_number=i,
                                       weight=Decimal(str(w)), reps=reps)
    return s


class ToolSchemaSemanticsTests(TestCase):
    """The two surfaces are described by ROLE, unambiguously."""

    def test_history_declares_aggregate_and_disclaims_record_detail(self):
        d = _desc("get_history")
        self.assertIn("aggregate", d)
        self.assertIn("how many workouts", d)                    # count example
        self.assertIn("does not return", d)                      # explicit disclaimer
        for w in ("exercise", "sets", "reps", "weights"):
            self.assertIn(w, d)                                  # names what it lacks
        self.assertIn("get_entity", d)                           # redirects detail Qs

    def test_entity_declares_record_detail_with_workout_examples(self):
        d = _desc("get_entity")
        self.assertIn("detail", d)
        for q in ("what exercises did i do", "did i do calf raises",
                  "what weight and reps", "summarize my last workout"):
            self.assertIn(q, d)                                  # explicit workout detail Qs
        self.assertIn("get_history", d)                          # redirects aggregate Qs

    def test_descriptions_hide_internal_implementation_names(self):
        for name in ("get_history", "get_entity"):
            raw = next(t for t in truth_tools()
                       if t["function"]["name"] == name)["function"]["description"]
            self.assertNotIn("CompleteEntity", raw)
            self.assertNotIn("DomainTruth", raw)


class CapabilityIndexRoleTests(TestCase):
    def test_capability_index_carries_distinct_semantic_roles(self):
        caps = _capabilities()
        self.assertIn("surface_roles", caps)
        self.assertIn("aggregate", caps["surface_roles"]["truth_history"].lower())
        self.assertIn("detail", caps["surface_roles"]["truth_entities"].lower())
        self.assertNotEqual(caps["surface_roles"]["truth_history"],
                            caps["surface_roles"]["truth_entities"])

    def test_note_disambiguates_the_workouts_vs_workout_collision(self):
        note = _capabilities()["note"].lower()
        self.assertIn("workouts", note)
        self.assertIn("workout", note)
        self.assertIn("different surfaces", note)

    def test_both_maps_still_present_catalog_driven(self):
        caps = _capabilities()
        self.assertIn("truth_history", caps)
        self.assertIn("truth_entities", caps)


class WorkoutSurfaceGranularityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="tsc@test.com", password="x")
        _workout(cls.user, date.today() - timedelta(days=1), "Leg Day",
                 [("Calf Raise", [(45, 12), (45, 12), (45, 12)]),
                  ("Squat", [(135, 10), (135, 10)])])

    # --- history 'workouts' = session count; NEVER exercise detail ---
    def test_history_workouts_is_aggregate_never_exercise_detail(self):
        r = get_domain_history(self.user, "health", "workouts", period="last_week")
        self.assertEqual(r["granularity"], "aggregate")
        self.assertIn("get_entity", r["scope"])
        blob = json.dumps(r).lower()
        self.assertNotIn("calf raise", blob)          # history carries no exercise names
        if r["status"] == "ready":
            self.assertEqual(r.get("unit"), "sessions")

    # --- entity 'workout' = full record detail incl. exercise names/sets ---
    def test_entity_workout_carries_record_detail(self):
        r = get_domain_entity(self.user, "health", entity_type="workout")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["granularity"], "record_detail")
        self.assertIn("get_history", r["scope"])
        names = [x["name"] for e in r["entities"]
                 for x in e["definition"]["exercises"]]
        self.assertIn("Calf Raise", names)

    # --- both surfaces are catalog-driven for health ---
    def test_health_participates_in_both_catalogs(self):
        self.assertIn("workouts", history_capability_index().get("health", ()))
        self.assertIn("workout", entity_capability_index().get("health", ()))


class SurfaceAuditDistinctionTests(TestCase):
    """The per-turn audit ledger records WHICH surface answered — the deterministic
    production check (ToolCallLog kind='truth') for the "which tool fired" question."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="aud@test.com", password="x")
        _workout(cls.user, date.today(), "Push Day", [("Bench", [(135, 8)])])

    def test_dispatch_records_the_answering_surface_by_name(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from apps.ai.models import ToolCallLog
        svc = ModelInterfaceService(self.user, ai_service=object())
        dispatch = svc._make_dispatch(turn_id="t1", surface="chat", tools_called=[])
        dispatch("get_entity", {"domain": "health", "entity_type": "workout"})
        dispatch("get_history", {"domain": "health", "metric": "workouts",
                                 "period": "last_week"})
        logged = set(ToolCallLog.objects.filter(
            user=self.user, kind="truth").values_list("tool_name", flat=True))
        self.assertIn("get_entity", logged)
        self.assertIn("get_history", logged)
