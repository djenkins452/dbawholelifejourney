# ==============================================================================
# File: apps/ai/tests/test_health_narration_guard.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The run_reasoning banned-language guard must protect HEALTH LLM
#   narration too — not just goals. An LLM health answer that leaks a coaching
#   phrase ("keep momentum") must be replaced by the clean deterministic fallback.
#   Origin: production full/full — health overall_progress leaked banned_phrase
#   "keep momentum" (the guard was gated to GOAL_INTENTS only).
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos.reasoning.plan import synthesize_plan
from apps.ai.chatgpt_cos.reasoning.stages import (
    run_reasoning, _answer_violation, HEALTH_INTENTS, GOAL_INTENTS,
)

User = get_user_model()
_CALL_API = "apps.ai.services.ai_service._call_api"

# A health working-memory rich enough that the deterministic fallback renders a
# real, non-empty answer (so we validate the ACTUAL rendered response).
_HEALTH_WM = {"intent": "overall_progress", "facts": {
    "current_status": {"weight_current": 232, "weight_unit": "lb",
                       "latest_glucose": 99, "sleep_avg_hours_7d": 6.4},
    "trends": {"weight_trend": "trending down"},
    "ranked_concerns": [{"concern": "sleep is averaging under 6.5 hours",
                         "action": "a consistent wind-down time"}],
}}

# An LLM answer that leaks the exact production coaching phrase.
_LEAKY = ("You're making solid progress on your health goals. Your weight is "
          "trending down and glucose is well-managed. Keep momentum going and "
          "stay consistent with sleep.")


class HealthNarrationGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="hgrd@example.com", password="x")

    def test_guard_replaces_leaky_health_llm_answer(self):
        plan = synthesize_plan("overall_progress")
        with mock.patch(_CALL_API, return_value=_LEAKY):
            answer, used_fallback = run_reasoning(self.user, "how is my health?",
                                                  plan, _HEALTH_WM)
        # the leaking LLM answer was rejected and replaced by the deterministic floor
        self.assertTrue(used_fallback)
        self.assertEqual(ar.banned_hits(answer), [], f"banned leak survived: {answer!r}")
        self.assertIn("weight", answer.lower())          # real rendered health content

    def test_clean_health_llm_answer_is_kept(self):
        plan = synthesize_plan("overall_progress")
        clean = "Your weight is trending down and glucose is in a good range."
        with mock.patch(_CALL_API, return_value=clean):
            answer, used_fallback = run_reasoning(self.user, "how is my health?",
                                                  plan, _HEALTH_WM)
        self.assertFalse(used_fallback)
        self.assertEqual(answer, clean)

    def test_violation_detects_banned_for_every_intent(self):
        # the BANNED-language check must flag coaching for health intents, not only
        # goals (the defect class: the guard was GOAL_INTENTS-gated).
        for intent in HEALTH_INTENTS + GOAL_INTENTS:
            self.assertIsNotNone(_answer_violation(intent, "Just keep momentum."),
                                 f"{intent} not guarded against banned coaching")

    def test_clean_health_text_is_not_flagged(self):
        # health intents carry no required-token rule, so clean prose passes.
        for intent in HEALTH_INTENTS:
            self.assertIsNone(_answer_violation(intent, "Your glucose is 99 mg/dL."),
                              f"{intent} false-positive on clean text")

    def test_health_deterministic_fallback_is_banned_free(self):
        from apps.ai.chatgpt_cos.reasoning.stages import _health_progress_fallback
        out = _health_progress_fallback(_HEALTH_WM)
        self.assertTrue(out.strip())
        self.assertEqual(ar.banned_hits(out), [])
