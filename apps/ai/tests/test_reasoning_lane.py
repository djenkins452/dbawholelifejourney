# ==============================================================================
# File: apps/ai/tests/test_reasoning_lane.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane — Planner -> Retrieval -> Working Memory -> Reasoning
# ==============================================================================
"""
Validates the reasoning-lane framework (milestone: 2 intents):

  Planner LLM (structured plan, never answers) -> deterministic authoritative
  retrieval -> curated working memory (no raw SAE) -> one plain _call_api
  reasoning (+ deterministic fallback). No agentic tool loop.
"""

import contextlib
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.reasoning import answer_reasoning_question
from apps.ai.chatgpt_cos.reasoning.plan import parse_plan
from apps.ai.chatgpt_cos.reasoning.stages import (
    build_working_memory,
    retrieve_truth,
    run_reasoning,
)

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"

_RISK_PLAN_JSON = json.dumps({
    "intent": "biggest_risk", "response_mode": "reasoning",
    "domains": ["health"], "required_truth": ["risk_decision", "health_state"],
    "optional_truth": ["foundational_health"], "reasoning_style": "risk_triage",
    "urgency": "high", "confidence": 0.9,
})
_PROGRESS_PLAN_JSON = json.dumps({
    "intent": "overall_progress", "response_mode": "mixed",
    "domains": ["health", "goals"],
    "required_truth": ["standing_context", "goals_state"],
    "optional_truth": ["execution_decision", "foundational_health"],
    "reasoning_style": "holistic_review", "urgency": "normal", "confidence": 0.85,
})
_OTHER_PLAN_JSON = json.dumps({
    "intent": "other", "response_mode": "lookup", "domains": [],
    "required_truth": [], "optional_truth": [], "reasoning_style": "",
    "urgency": "low", "confidence": 0.5,
})

_DECISION = {"mode": "risk", "primary_action": {"title": "Recheck BP"},
             "reason": "BP elevated", "message": "Your BP is trending high.",
             "follow_on": None}


@contextlib.contextmanager
def _mock_providers():
    with mock.patch("apps.ai.cos_services.get_domain_state",
                    side_effect=lambda u, d: {"status": "ready", "domain": d,
                                              "state": {"weight_current": 298.3,
                                                        "bp_systolic": 111,
                                                        "bp_diastolic": 72,
                                                        "_huge": list(range(100))}}), \
         mock.patch("apps.ai.cos_services.get_standing_context",
                    return_value={"status": "ready", "recommended_focus": "health"}), \
         mock.patch("apps.ai.cos_services.get_foundational_health_facts",
                    return_value={"current_weight": {"value": 298.3, "unit": "lb"}}), \
         mock.patch("apps.ai.cos_mode_router.normalize_mode", side_effect=lambda m: m), \
         mock.patch("apps.core.execution.execution_state.build_execution_state",
                    return_value={}), \
         mock.patch("apps.core.execution.selectors.select", return_value=_DECISION):
        yield


class PlanParsingTests(TestCase):
    def test_valid_plan(self):
        p = parse_plan(_RISK_PLAN_JSON)
        self.assertEqual(p.intent, "biggest_risk")
        self.assertEqual(p.required_truth, ["risk_decision", "health_state"])
        self.assertEqual(p.urgency, "high")

    def test_code_fenced_json(self):
        p = parse_plan("```json\n" + _RISK_PLAN_JSON + "\n```")
        self.assertEqual(p.intent, "biggest_risk")

    def test_unknown_truth_keys_dropped(self):
        bad = json.dumps({"intent": "biggest_risk", "response_mode": "reasoning",
                          "domains": ["health", "atlantis"],
                          "required_truth": ["risk_decision", "made_up_source"],
                          "optional_truth": [], "reasoning_style": "x",
                          "urgency": "high", "confidence": 1.0})
        p = parse_plan(bad)
        self.assertEqual(p.domains, ["health"])           # atlantis dropped
        self.assertEqual(p.required_truth, ["risk_decision"])  # made_up dropped

    def test_unknown_intent_becomes_other(self):
        p = parse_plan(json.dumps({"intent": "diagnose_me", "response_mode": "x"}))
        self.assertEqual(p.intent, "other")

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_plan("not json at all"))
        self.assertIsNone(parse_plan(""))


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class StageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_stage@example.com", password="x")

    def test_retrieve_truth_fetches_planned_keys(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        with _mock_providers():
            truth = retrieve_truth(self.user, plan)
        self.assertIn("risk_decision", truth)
        self.assertIn("health_state", truth)
        self.assertIn("foundational_health", truth)

    def test_working_memory_curated_no_raw_sae(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        with _mock_providers():
            truth = retrieve_truth(self.user, plan)
        wm = build_working_memory(plan, truth)
        # health_state curated to whitelist scalars; the raw "_huge" list is gone
        hs = wm["facts"]["health_state"]
        self.assertIn("weight_current", hs)
        self.assertNotIn("_huge", hs)
        self.assertEqual(hs["bp_systolic"], 111)
        # decision curated to action/reason/recommendation
        self.assertEqual(wm["facts"]["risk_decision"]["recommendation"],
                         "Your BP is trending high.")

    def test_run_reasoning_uses_plain_call_api(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        wm = {"intent": "biggest_risk", "facts": {"risk_decision":
              {"recommendation": "Your BP is trending high."}}}
        with mock.patch(_CALL_API, return_value="Your biggest risk is BP.") as ca, \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            answer, fb = run_reasoning(self.user, "risk?", plan, wm)
        self.assertEqual(answer, "Your biggest risk is BP.")
        self.assertFalse(fb)
        _, kwargs = ca.call_args
        self.assertNotIn("tools", kwargs)

    def test_run_reasoning_deterministic_fallback(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        wm = {"intent": "biggest_risk", "facts": {"risk_decision":
              {"recommendation": "Your BP is trending high."}}}
        with mock.patch(_CALL_API, return_value=None):
            answer, fb = run_reasoning(self.user, "risk?", plan, wm)
        self.assertTrue(fb)
        self.assertEqual(answer, "Your BP is trending high.")


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_eng@example.com", password="x")

    def test_biggest_risk_end_to_end_no_tool_loop(self):
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[_RISK_PLAN_JSON, "Your biggest risk is BP."]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What is my biggest health risk right now?")
        self.assertIsNotNone(out)
        self.assertEqual(out["fast_path"], "reasoning")
        self.assertEqual(out["reasoning"]["intent"], "biggest_risk")
        self.assertEqual(out["answer"], "Your biggest risk is BP.")
        self.assertIn("risk_decision", out["reasoning"]["truth_keys"])

    def test_overall_progress_end_to_end(self):
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[_PROGRESS_PLAN_JSON, "You're trending well."]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "How am I doing overall with my health goals?")
        self.assertEqual(out["reasoning"]["intent"], "overall_progress")
        self.assertEqual(out["answer"], "You're trending well.")

    def test_other_intent_declines(self):
        with mock.patch(_CALL_API, return_value=_OTHER_PLAN_JSON):
            out = answer_reasoning_question(self.user, "Tell me a joke.")
        self.assertIsNone(out)

    def test_planner_unavailable_declines(self):
        with mock.patch(_CALL_API, return_value=None):
            out = answer_reasoning_question(self.user, "What is my biggest risk?")
        self.assertIsNone(out)

    def test_reasoning_fallback_when_llm_empty(self):
        # planner succeeds, reasoning call returns empty -> deterministic fallback
        with _mock_providers(), \
             mock.patch(_CALL_API, side_effect=[_RISK_PLAN_JSON, None]):
            out = answer_reasoning_question(
                self.user, "What is my biggest health risk right now?")
        self.assertTrue(out["reasoning"]["used_fallback"])
        self.assertEqual(out["answer"], "Your BP is trending high.")
