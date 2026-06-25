# ==============================================================================
# File: apps/ai/tests/test_reasoning_lane.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane — health-scoped intents (no cross-domain contamination)
# ==============================================================================
"""
Validates the reasoning-lane framework + the health-scope contamination fix:

  Planner (structured plan) -> deterministic authoritative retrieval (health
  intents SCOPED to health truth) -> HealthWorkingMemoryCurator (health truth
  ONLY) -> one plain _call_api reasoning (+ deterministic health fallback).

Regression: health reasoning must NEVER receive tasks / generic decisions
(the "overdue Harley task" contamination).
"""

import contextlib
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.reasoning import answer_reasoning_question
from apps.ai.chatgpt_cos.reasoning.plan import parse_plan
from apps.ai.chatgpt_cos.reasoning.stages import (
    REASONING_PROFILES,
    _calibrate_label,
    _intra_day_hint,
    _nutrition_time_context,
    build_working_memory,
    health_working_memory,
    retrieve_truth,
    run_reasoning,
)

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"
_BUILD_EXEC = "apps.core.execution.execution_state.build_execution_state"

# A CONTAMINATED plan (the planner mistakenly requests cross-domain truth) — the
# health scope must drop risk_decision/execution_decision before retrieval.
_RISK_PLAN_JSON = json.dumps({
    "intent": "biggest_health_risk", "response_mode": "reasoning",
    "domains": ["health"],
    "required_truth": ["risk_decision", "execution_decision", "health_state"],
    "optional_truth": ["foundational_health"], "reasoning_style": "risk_triage",
    "urgency": "high", "confidence": 0.9,
})
_PROGRESS_PLAN_JSON = json.dumps({
    "intent": "overall_progress", "response_mode": "mixed",
    "domains": ["health"],
    "required_truth": ["health_state", "foundational_health"],
    "optional_truth": [], "reasoning_style": "holistic_review",
    "urgency": "normal", "confidence": 0.85,
})
_OTHER_PLAN_JSON = json.dumps({"intent": "other", "response_mode": "lookup",
                               "domains": [], "required_truth": [],
                               "optional_truth": [], "reasoning_style": "",
                               "urgency": "low", "confidence": 0.5})

# A task-shaped decision — if this ever reaches health working memory, the test fails.
_TASK_DECISION = {"mode": "risk", "primary_action": {"type": "task",
                  "title": "Wake up", "source": "routine"},
                  "reason": "overdue", "message": "Biggest risk: Wake up."}

_HEALTH_STATE = {"status": "ready", "domain": "health", "state": {
    "weight_current": 298.3, "weight_unit": "lb", "weight_trend": "decreasing",
    "bp_systolic": 111, "bp_diastolic": 72, "sleep_avg_hours_7d": 6.7,
    "weight_goal": 240.0, "weight_goal_remaining": 58.3,
    "weight_goal_on_track": False, "plateau_risk_label": "Elevated",
    "_huge": list(range(100)),
}}


@contextlib.contextmanager
def _mock_providers():
    with mock.patch("apps.ai.cos_services.get_domain_state",
                    side_effect=lambda u, d: _HEALTH_STATE), \
         mock.patch("apps.ai.cos_services.get_foundational_health_facts",
                    return_value={"current_weight": {"value": 298.3, "unit": "lb"}}), \
         mock.patch(_BUILD_EXEC, return_value={}) as bes, \
         mock.patch("apps.core.execution.selectors.select",
                    return_value=_TASK_DECISION):
        yield bes


class PlanParsingTests(TestCase):
    def test_valid_plan(self):
        p = parse_plan(_RISK_PLAN_JSON)
        self.assertEqual(p.intent, "biggest_health_risk")

    def test_unknown_intent_becomes_other(self):
        self.assertEqual(parse_plan('{"intent":"x"}').intent, "other")

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_plan("not json"))


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class HealthScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_scope@example.com", password="x")

    def test_scope_drops_cross_domain_truth_and_never_fetches_it(self):
        plan = parse_plan(_RISK_PLAN_JSON)   # requests risk_decision + execution_decision
        with _mock_providers() as bes:
            truth = retrieve_truth(self.user, plan)
        # generic/cross-domain decisions DROPPED by the health scope:
        self.assertNotIn("risk_decision", truth)
        self.assertNotIn("execution_decision", truth)
        # health truth retained:
        self.assertIn("health_state", truth)
        self.assertIn("foundational_health", truth)
        # the decision engine was never even invoked:
        bes.assert_not_called()

    def test_health_working_memory_is_health_only(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        with _mock_providers():
            truth = retrieve_truth(self.user, plan)
        wm = build_working_memory(plan, truth)
        facts = wm["facts"]
        # curated health buckets present
        self.assertIn("current_status", facts)
        self.assertIn("active_risks", facts)
        self.assertEqual(facts["current_status"]["bp_systolic"], 111)
        self.assertFalse(facts["active_risks"]["weight_goal_on_track"])
        # NO contamination, NO raw SAE
        blob = json.dumps(wm, default=str)
        self.assertNotIn("risk_decision", blob)
        self.assertNotIn("Wake up", blob)
        self.assertNotIn("routine", blob)
        self.assertNotIn("_huge", blob)

    def test_curator_reads_only_health_truth(self):
        # even handed contaminated truth directly, the curator ignores non-health
        contaminated = {"health_state": _HEALTH_STATE,
                        "risk_decision": _TASK_DECISION}
        facts = health_working_memory(contaminated)
        self.assertNotIn("risk_decision", json.dumps(facts, default=str))
        self.assertNotIn("Wake up", json.dumps(facts, default=str))


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class ReasonerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_reason@example.com", password="x")

    def test_reasoning_uses_plain_call_api(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        wm = {"intent": "biggest_health_risk",
              "facts": {"active_risks": {"weight_goal_on_track": False}}}
        with mock.patch(_CALL_API, return_value="Your BP needs attention.") as ca, \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            answer, fb = run_reasoning(self.user, "risk?", plan, wm)
        self.assertEqual(answer, "Your BP needs attention.")
        self.assertNotIn("tools", ca.call_args.kwargs)

    def test_health_fallback_is_health_only(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        wm = {"intent": "biggest_health_risk", "facts": {"active_risks":
              {"weight_goal_on_track": False, "plateau_risk_label": "Elevated"}}}
        with mock.patch(_CALL_API, return_value=None):
            answer, fb = run_reasoning(self.user, "risk?", plan, wm)
        self.assertTrue(fb)
        self.assertIn("weight goal", answer.lower())
        self.assertNotIn("wake up", answer.lower())


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_eng@example.com", password="x")

    def test_biggest_health_risk_no_contamination(self):
        # planner emits a CONTAMINATED plan; result must still be health-only.
        with _mock_providers(), \
             mock.patch(_CALL_API, side_effect=[_RISK_PLAN_JSON, None]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What is my biggest health risk right now?")
        self.assertEqual(out["reasoning"]["intent"], "biggest_health_risk")
        self.assertNotIn("risk_decision", out["reasoning"]["truth_keys"])
        self.assertNotIn("Wake up", out["answer"])
        self.assertNotIn("Harley", out["answer"])

    def test_overall_progress_end_to_end(self):
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[_PROGRESS_PLAN_JSON, "You're behind on weight."]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "How am I doing overall with my health goals?")
        self.assertEqual(out["reasoning"]["intent"], "overall_progress")
        self.assertEqual(out["answer"], "You're behind on weight.")

    def test_other_intent_declines(self):
        with mock.patch(_CALL_API, return_value=_OTHER_PLAN_JSON):
            self.assertIsNone(answer_reasoning_question(self.user, "Tell a joke."))

    def test_planner_unavailable_declines(self):
        with mock.patch(_CALL_API, return_value=None):
            self.assertIsNone(answer_reasoning_question(self.user, "biggest risk?"))


class ToneCalibrationTests(TestCase):  # Fix 3
    def test_severe_labels_softened(self):
        self.assertEqual(_calibrate_label("Significant"), "elevated — worth watching")
        self.assertEqual(_calibrate_label("Critical"), "worth attention")
        self.assertEqual(_calibrate_label("dangerous"), "worth watching")

    def test_non_severe_labels_unchanged(self):
        self.assertEqual(_calibrate_label("Elevated"), "Elevated")
        self.assertEqual(_calibrate_label("stable"), "stable")
        self.assertEqual(_calibrate_label(False), False)

    def test_curator_calibrates_active_risk_labels(self):
        truth = {"health_state": {"state": {
            "muscle_loss_risk_level": "significant", "weight_goal_on_track": False}}}
        facts = health_working_memory(truth)
        self.assertEqual(facts["active_risks"]["muscle_loss_risk_level"],
                         "elevated — worth watching")

    def test_prompts_carry_calibration_and_no_alarmist_words(self):
        for intent in ("biggest_health_risk", "overall_progress"):
            sys = REASONING_PROFILES[intent]["system"].lower()
            self.assertIn("worth watching", sys)
            self.assertIn("evidence-based", sys)


class NutritionTimeAwarenessTests(TestCase):  # Fix 2
    def test_intra_day_hints(self):
        self.assertEqual(_intra_day_hint(0, 176, 40, "morning"),
                         "early_day_not_yet_logged")
        self.assertEqual(_intra_day_hint(20, 176, 40, "morning"),
                         "logging_in_progress")
        self.assertEqual(_intra_day_hint(0, 176, 40, "evening"),
                         "nothing_logged_today")
        self.assertEqual(_intra_day_hint(50, 176, 40, "evening"),
                         "below_typical_for_time_of_day")
        self.assertEqual(_intra_day_hint(150, 176, 40, "evening"),
                         "on_track_for_time_of_day")

    def test_nutrition_context_morning_zero_not_a_risk(self):
        from types import SimpleNamespace
        nut = {"daily_protein_g": 0.0, "rolling_7d_protein_avg": 176.9,
               "protein_target": 40.0, "daily_calories": 0.0,
               "rolling_7d_calories_avg": 1993.5, "calorie_target": 2000}
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value=nut), \
             mock.patch("apps.core.utils.get_user_now",
                        return_value=SimpleNamespace(hour=9)):
            ctx = _nutrition_time_context(object())
        self.assertEqual(ctx["day_phase"], "morning")
        self.assertEqual(ctx["protein_g"]["interpretation"],
                         "early_day_not_yet_logged")
        self.assertEqual(ctx["protein_g"]["typical_7d_avg"], 176.9)

    def test_curator_includes_nutrition_context_when_user_given(self):
        from types import SimpleNamespace
        nut = {"daily_protein_g": 0.0, "rolling_7d_protein_avg": 176.9,
               "protein_target": 40.0}
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value=nut), \
             mock.patch("apps.core.utils.get_user_now",
                        return_value=SimpleNamespace(hour=9)):
            facts = health_working_memory({"health_state": {"state": {}}},
                                          user=object())
        self.assertIn("nutrition_context", facts)
