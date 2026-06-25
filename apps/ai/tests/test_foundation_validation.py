# ==============================================================================
# File: apps/ai/tests/test_foundation_validation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Foundation fact FAST PATH — deterministic, no tools, no agentic loop.
# ==============================================================================
"""
Validates the foundational-fact fast path:

    classify -> get_foundational_health_facts -> plain _call_api to phrase
    -> deterministic payload fallback if _call_api fails.

Success criteria: no _call_api_with_tools, no tools, no tool_choice, no legacy
Beth, exact fact returned (never empty).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.foundational_facts import (
    answer_foundational_fact,
    classify_foundational_fact,
    format_fact_sentence,
)

User = get_user_model()

_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"

_FAKE_STATE = {
    "health": {
        "weight_current": 298.3, "weight_unit": "lb", "weight_trend": "decreasing",
        "last_weight_entry": "2026-04-07T16:00:00+00:00",
        "latest_glucose": 133.0, "latest_glucose_unit": "mg/dL",
        "last_glucose_entry": "2026-04-07T20:43:35+00:00",
        "sleep_avg_hours_7d": 6.7, "sleep_trend": "decreasing",
        "last_sleep_entry": "2026-04-07",
    },
    "medicine": {"active_medications": ["Metformin HCL ER", "Valsartan"],
                 "medication_count": 2},
    "nutrition": {"daily_calories": 1850.0, "calorie_target": 2000,
                  "daily_protein_g": 142.0, "protein_target": 180},
}

# prompt -> (fact key, substring that must appear in the deterministic answer)
PROMPTS = [
    ("What is my current weight?",                "current_weight",       "298.3"),
    ("What was my last glucose reading?",         "last_glucose_reading", "133"),
    ("What medications am I currently taking?",   "current_medications",  "Metformin"),
    ("How many calories have I consumed today?",  "calories_today",       "1850"),
    ("How much protein have I consumed today?",   "protein_today",        "142"),
    ("How did I sleep last night?",               "sleep_last_night",     "6.7"),
]


def _fake_module_state(user, module, allow_rebuild=False):
    return _FAKE_STATE.get(module, {})


class ClassifierTests(TestCase):
    def test_maps_each_foundational_prompt(self):
        for prompt, key, _ in PROMPTS:
            self.assertEqual(classify_foundational_fact(prompt), key, prompt)

    def test_non_foundational_returns_none(self):
        for prompt in ("How am I doing overall?",
                       "Help me think through my week.",
                       "What patterns do you see in my health?",
                       "What should I focus on today?"):
            self.assertIsNone(classify_foundational_fact(prompt), prompt)


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class FastPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="ff@example.com", password="x")
        cls.user.preferences.use_chatgpt_cos = True
        cls.user.preferences.save()

    def test_fast_path_uses_plain_call_api_never_tool_loop(self):
        for prompt, key, _ in PROMPTS:
            with self.subTest(prompt=prompt), \
                 mock.patch(_GMS, side_effect=_fake_module_state), \
                 mock.patch(_CALL_API, return_value="Phrased answer.") as ca, \
                 mock.patch(_CALL_API_TOOLS,
                            side_effect=AssertionError("tool loop used")) as cwt:
                out = answer_foundational_fact(self.user, prompt)

            self.assertIsNotNone(out, prompt)
            self.assertEqual(out["fact_key"], key)
            self.assertEqual(out["tools_called"], ["get_foundational_health_facts"])
            self.assertEqual(out["tools_advertised"], [])
            self.assertEqual(out["answer"], "Phrased answer.")
            self.assertEqual(out["fast_path"], "foundational_fact")
            self.assertTrue(ca.called)
            self.assertFalse(cwt.called)
            # The phrasing call carries NO tools / tool_choice.
            _, kwargs = ca.call_args
            self.assertNotIn("tools", kwargs)
            self.assertNotIn("tool_choice", kwargs)

    def test_deterministic_fallback_when_call_api_returns_none(self):
        for prompt, key, needle in PROMPTS:
            with self.subTest(prompt=prompt), \
                 mock.patch(_GMS, side_effect=_fake_module_state), \
                 mock.patch(_CALL_API, return_value=None):
                out = answer_foundational_fact(self.user, prompt)
            self.assertTrue(out["answer"])                  # never empty
            self.assertIn(needle, out["answer"])            # exact fact present

    def test_deterministic_fallback_when_call_api_raises(self):
        with mock.patch(_GMS, side_effect=_fake_module_state), \
             mock.patch(_CALL_API, side_effect=RuntimeError("boom")):
            out = answer_foundational_fact(self.user, "What is my current weight?")
        self.assertIn("298.3", out["answer"])

    def test_non_foundational_prompt_returns_none(self):
        self.assertIsNone(
            answer_foundational_fact(self.user, "How am I doing overall?"))

    def test_generate_takes_fast_path_not_tool_loop(self):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        from apps.ai.models import AssistantConversation

        conv = AssistantConversation.get_or_create_active(self.user)
        with mock.patch(_GMS, side_effect=_fake_module_state), \
             mock.patch("apps.core.ai_state.state_engine.get_user_state",
                        return_value={}), \
             mock.patch(_CALL_API, return_value="Your weight is 298.3 lb."), \
             mock.patch(_CALL_API_TOOLS,
                        side_effect=AssertionError("tool loop used")):
            result = ChatGPTCoSService(self.user).generate(
                conv, "What is my current weight?")
        self.assertEqual(result.get("fast_path"), "foundational_fact")
        self.assertEqual(result["answer"], "Your weight is 298.3 lb.")
        self.assertIsNone(result.get("empty_reason"))


class FormatFactSentenceTests(TestCase):
    def test_each_key_surfaces_value(self):
        cases = {
            "current_weight": ({"value": 298.3, "unit": "lb",
                                "trend": "decreasing"}, "298.3"),
            "last_glucose_reading": ({"value": 133.0, "unit": "mg/dL"}, "133"),
            "current_medications": ({"value": ["Metformin", "Valsartan"],
                                     "count": 2}, "Metformin"),
            "calories_today": ({"value": 1850.0, "target": 2000}, "1850"),
            "protein_today": ({"value": 142.0, "target": 180}, "142"),
            "sleep_last_night": ({"value": 6.7, "unit": "hours",
                                  "trend": "decreasing"}, "6.7"),
            "average_sleep_7d": ({"value": 6.7, "unit": "hours"}, "6.7"),
            "sleep_trend": ({"value": "decreasing"}, "decreasing"),
        }
        for key, (fact, needle) in cases.items():
            self.assertIn(needle, format_fact_sentence(key, fact), key)

    def test_unknown_status_is_explicit(self):
        s = format_fact_sentence("current_weight",
                                 {"status": "unknown", "reason": "x"})
        self.assertIn("don't have", s)

    def test_zero_is_a_valid_value(self):
        s = format_fact_sentence("calories_today", {"value": 0.0, "target": 2000})
        self.assertIn("0.0 calories", s)
