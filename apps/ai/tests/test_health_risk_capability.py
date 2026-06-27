# ==============================================================================
# File: apps/ai/tests/test_health_risk_capability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Health-risk DETERMINISTIC CAPABILITY GAP. Health concern/risk/problem
#   phrasing must reach the deterministic biggest_health_risk path even with OpenAI
#   DISABLED — WLJ owns health truth, so these must never fall to the tool loop /
#   emergency fallback. Origin: production full/deep RED — biggest_health_risk__1/__2
#   returned the assistant-unavailable message (openai=False, intent/lane/fallback all
#   missing). Validates ACTUAL rendered responses, not templates.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.reasoning.plan import deterministic_intent
from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.chatgpt_cos import acceptance_rules as ar

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"

# The exact real-user variants (the two failing production questions + paraphrases).
HEALTH_RISK_VARIANTS = [
    "What health issue concerns you most?",
    "What is the main health problem I should focus on?",
    "What is my biggest health risk?",
    "What should I be watching with my health?",
    "Is anything concerning in my health right now?",
    "What's my biggest health concern?",
]


class HealthRiskRoutingTests(SimpleTestCase):
    def test_all_variants_route_deterministically_to_biggest_health_risk(self):
        for q in HEALTH_RISK_VARIANTS:
            self.assertEqual(deterministic_intent(q), "biggest_health_risk", q)

    def test_health_progress_questions_unchanged(self):
        # the additive risk signals must NOT steal progress/summary questions.
        for q in ("How am I doing overall with my health goals?",
                  "Give me a health summary.", "Am I making progress with my health?"):
            self.assertEqual(deterministic_intent(q), "overall_progress", q)


class HealthRiskDeterministicAnswerTests(TestCase):
    """End-to-end: with OpenAI DISABLED, each variant produces a deterministic
    health answer — never the assistant-unavailable / outage message."""
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="hrc@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def test_variants_answer_with_openai_disabled(self):
        with mock.patch(_C, side_effect=RuntimeError("openai down")), \
             mock.patch(_CT, side_effect=RuntimeError("openai down")):
            for q in HEALTH_RISK_VARIANTS:
                res = route_message(self.u, q, None)
                self.assertIsNotNone(res, f"{q!r} fell to the tool loop (capability gap)")
                ans = (res.get("answer") or "").strip()
                self.assertTrue(ans, f"{q!r} empty")
                self.assertEqual(res.get("lane"), "personal_reasoning", q)
                self.assertFalse(ar.is_failure_message(ans),
                                 f"{q!r} returned assistant-unavailable: {ans[:80]!r}")
                self.assertNotIn("couldn't pull that together", ans.lower())


class DeepCoverageTests(SimpleTestCase):
    def test_all_variants_are_in_the_deep_bank(self):
        deep_texts = {q["text"].lower() for q in ar.questions_for("health", "deep")}
        for v in ("what health issue concerns you most?",
                  "what is the main health problem i should focus on?",
                  "what should i be watching with my health?",
                  "is anything concerning in my health right now?"):
            self.assertIn(v, deep_texts, f"Deep bank missing: {v!r}")
