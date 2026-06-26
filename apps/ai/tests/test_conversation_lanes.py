# ==============================================================================
# File: apps/ai/tests/test_conversation_lanes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Conversation lane registry — clarification + general lanes.
# ==============================================================================
"""
Proves the framework-first lane registry (P6/P13):
  Foundational Facts -> Personal Reasoning -> Clarification -> General -> (tool loop)

Guarantees under test:
  * 'check in' routes to the Clarification lane with Daily Check-In framing
  * clarification is DETERMINISTIC (no OpenAI) and never reaches the tool loop
  * the General lane is SANDBOXED (no personal data) with a deterministic fallback
  * existing health-intent routing is preserved (new lanes never steal it)
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.lanes import (
    AMBIGUITY_TYPES,
    LANE_REGISTRY,
    clarify,
    general_answer,
    route_message,
)

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"
_FOUNDATIONAL = "apps.ai.chatgpt_cos.foundational_facts.answer_foundational_fact"
_REASONING = "apps.ai.chatgpt_cos.reasoning.answer_reasoning_question"

_HEALTH_QS = (
    "What is my biggest health risk right now?",
    "How am I doing overall with my health goals?",
    "What should I focus on from a health perspective today?",
    "What are my health concerns?",
)


class ClarificationLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_clar@example.com", password="x")

    def test_daily_checkin_type_registered(self):
        types = {a["type"] for a in AMBIGUITY_TYPES}
        self.assertIn("daily_checkin_candidate", types)

    def test_clarify_check_in_is_deterministic_no_openai(self):
        # clarify() itself must never call OpenAI: mock both APIs to explode.
        with mock.patch(_CALL_API, side_effect=AssertionError("openai")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = clarify("check in")
        self.assertIsNotNone(out)
        self.assertEqual(out["ambiguity_type"], "daily_checkin_candidate")
        self.assertEqual(out["lane"], "clarification")
        self.assertIn("daily check-in", out["answer"].lower())
        for opt in ("coming up today", "do next", "health and energy",
                    "goals and commitments", "whole life check-in"):
            self.assertIn(opt, out["answer"].lower())

    def test_check_in_routes_to_clarification_not_tool_loop_no_openai_required(self):
        # Even with OpenAI DOWN (planner raises), 'check in' still produces the
        # deterministic clarification and NEVER reaches the tool loop.
        with mock.patch(_CALL_API, side_effect=RuntimeError("openai down")), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")):
            out = route_message(self.user, "check in")
        self.assertEqual(out["lane"], "clarification")
        self.assertEqual(out["ambiguity_type"], "daily_checkin_candidate")
        self.assertIn("daily check-in", out["answer"].lower())

    def test_help_and_review_clarifications(self):
        self.assertEqual(clarify("help me")["ambiguity_type"], "unspecified_help")
        self.assertEqual(clarify("review this")["ambiguity_type"],
                         "unspecified_review")

    def test_specific_request_not_stolen_into_clarification(self):
        # a specific, longer request is NOT claimed as ambiguous
        self.assertIsNone(clarify("check in on my flight to Denver tomorrow morning"))
        self.assertIsNone(clarify("review my Q3 sales report and summarize risks"))


class GeneralLaneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_gen@example.com", password="x")

    def test_general_knowledge_routes_to_general(self):
        with mock.patch(_CALL_API,
                        return_value="Abraham Lincoln was the 16th US president."), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tool loop")), \
             mock.patch(_FOUNDATIONAL, return_value=None):
            out = route_message(self.user, "Who was Abraham Lincoln?")
        self.assertEqual(out["lane"], "general_conversation")
        self.assertIn("Lincoln", out["answer"])

    def test_general_is_sandboxed_no_personal_payload(self):
        captured = {}

        def _spy(system, user_prompt, **kw):
            captured["system"] = system
            captured["user_prompt"] = user_prompt
            return "Photosynthesis converts light into chemical energy."

        with mock.patch(_CALL_API, side_effect=_spy):
            out = general_answer(self.user, "Explain photosynthesis.")
        self.assertEqual(out["lane"], "general_conversation")
        # the prompt carries ONLY the question — no SAE / personal data injected
        self.assertEqual(captured["user_prompt"], "Explain photosynthesis.")
        self.assertIn("do not reference", captured["system"].lower())

    def test_general_deterministic_fallback_on_llm_failure(self):
        with mock.patch(_CALL_API, side_effect=RuntimeError("boom")):
            out = general_answer(self.user, "What is Delphi?")
        self.assertEqual(out["lane"], "general_conversation")
        self.assertTrue(out["answer"].strip())
        self.assertIn("try again", out["answer"].lower())

    def test_general_declines_personal_questions(self):
        for q in ("what is my weight", "what are my goals",
                  "how am I doing with my health"):
            self.assertIsNone(general_answer(self.user, q), q)


class RoutingPreservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="lane_route@example.com", password="x")

    def test_registry_order(self):
        self.assertEqual([n for n, _ in LANE_REGISTRY],
                         ["foundational_facts", "personal_reasoning",
                          "clarification", "general_conversation"])

    def test_health_questions_never_claimed_by_new_lanes(self):
        # The Clarification + General lanes must NEVER claim a health/personal
        # question — they would otherwise lose personalization / contaminate.
        for q in _HEALTH_QS + ("what's my weight", "what is my glucose today"):
            self.assertIsNone(clarify(q), f"clarify stole: {q}")
            self.assertIsNone(general_answer(self.user, q), f"general stole: {q}")

    def test_health_question_routes_to_reasoning_first(self):
        # Reasoning claims before Clarification/General are ever consulted.
        with mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_REASONING,
                        return_value={"answer": "health answer",
                                      "tools_called": [],
                                      "reasoning": {"intent": "biggest_health_risk"}}), \
             mock.patch("apps.ai.chatgpt_cos.lanes.clarify",
                        side_effect=AssertionError("clarify reached")), \
             mock.patch("apps.ai.chatgpt_cos.lanes.general_answer",
                        side_effect=AssertionError("general reached")):
            out = route_message(self.user, "What is my biggest health risk right now?")
        self.assertEqual(out["lane"], "personal_reasoning")
        self.assertEqual(out["answer"], "health answer")
        self.assertEqual(out["reasoning"]["intent"], "biggest_health_risk")

    def test_all_lanes_decline_returns_none_for_tool_loop(self):
        # Unknown / non-general / non-ambiguous -> route declines so the caller
        # runs the tool-loop terminal fallback (P8). Planner returns None.
        with mock.patch(_FOUNDATIONAL, return_value=None), \
             mock.patch(_CALL_API, return_value=None):
            self.assertIsNone(route_message(self.user, "asdf qwer zxcv"))

    def test_lane_results_carry_answer_and_tools_called(self):
        # contract parity — every lane result is task-compatible.
        c = clarify("check in")
        self.assertIn("answer", c)
        self.assertEqual(c["tools_called"], [])
        with mock.patch(_CALL_API, return_value="x"):
            g = general_answer(self.user, "What is gravity?")
        self.assertIn("answer", g)
        self.assertEqual(g["tools_called"], [])
