# ==============================================================================
# File: apps/ai/tests/test_p26_deep_hardening.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P26 Deep-suite hardening — three SYSTEMIC defect classes, each made
#   permanent by validating ACTUAL rendered responses (not templates):
#   DC#1 every CoS capability answers deterministically with OpenAI DISABLED;
#   DC#2 goal-meaning paraphrases resolve to goal reasoning;
#   DC#3 external/definitional questions never retrieve personal truth.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, external_general_signal,
)
from apps.ai.chatgpt_cos.reasoning import plan as planmod

User = get_user_model()
_CALL = "apps.ai.services.ai_service._call_api"
_CALLT = "apps.ai.services.ai_service._call_api_with_tools"


# ---------------------------------------------------------------------------
# DC#1 — every CoS capability answers DETERMINISTICALLY when OpenAI is disabled.
# ---------------------------------------------------------------------------
class CoSDeterministicDegradationTests(TestCase):
    COS_REQUESTS = [
        "what needs my attention?", "help me plan the rest of the day", "wrap up my day",
        "what should I know today?", "What's my biggest health risk right now?",
        "Give me a health summary.", "How is my diabetes doing?",
        "How am I doing overall with my health goals?", "what should I focus on today",
        "what comes next", "am I behind on this goal?",
    ]

    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p26cos@x.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def test_all_cos_requests_answer_without_openai(self):
        with mock.patch(_CALL, side_effect=RuntimeError("openai down")), \
             mock.patch(_CALLT, side_effect=RuntimeError("openai down")):
            for q in self.COS_REQUESTS:
                res = route_message(self.u, q, None)
                # A CoS capability must be claimed by a deterministic lane — never
                # fall through to the tool loop (which needs OpenAI).
                self.assertIsNotNone(res, f"{q!r} fell to the tool loop (no deterministic lane)")
                ans = (res.get("answer") or "").strip()
                self.assertTrue(ans, f"{q!r} produced an empty answer")
                # Personal CoS truth must NOT degrade to an OpenAI-outage message.
                self.assertFalse(ar.is_failure_message(ans),
                                 f"{q!r} degraded to an outage message: {ans[:80]!r}")

    def test_briefing_lane_is_deterministic_and_non_empty(self):
        from apps.ai.chatgpt_cos.lanes import _cos_briefing_lane
        for q in ("what needs my attention?", "help me plan the rest of the day",
                  "wrap up my day", "what should I know today?"):
            with mock.patch(_CALL, side_effect=RuntimeError("down")):
                res = _cos_briefing_lane(self.u, q, None)
            self.assertIsNotNone(res, q)
            self.assertEqual(res["lane"], "cos_briefing")
            self.assertTrue(res["answer"].strip())


# ---------------------------------------------------------------------------
# DC#2 — goal-meaning paraphrases resolve to goal reasoning (pure routing).
# ---------------------------------------------------------------------------
class GoalSemanticBreadthTests(SimpleTestCase):
    def _route(self, msg):
        return planmod.named_goal_intent(msg, [], None)[0]

    def test_failure_mode_paraphrases(self):
        for q in ("what should I watch out for?", "what could derail this?",
                  "what could go wrong with this?", "what would stop me?"):
            self.assertEqual(self._route(q), "goal_failure_modes", q)

    def test_move_forward_paraphrases(self):
        for q in ("move this forward", "how do I move this forward?",
                  "what's the highest leverage action?", "help me move the needle"):
            self.assertEqual(self._route(q), "goals_focus_today", q)

    def test_health_context_not_stolen_by_goal_breadth(self):
        # "watch out for" with health grounding must NOT become a goal intent.
        self.assertIsNone(planmod._foundational_goal_intent(
            "what should I watch out for with my health"))


# ---------------------------------------------------------------------------
# DC#3 — external/definitional questions never retrieve personal truth.
# ---------------------------------------------------------------------------
class PersonalExternalBoundaryTests(SimpleTestCase):
    # Explicitly framed external questions that CONTAIN a domain word — these need
    # the external signal to suppress personal retrieval.
    EXTERNAL_FRAMED = ["What is a healthy weight generally?", "What is normal blood pressure?",
                       "What is a healthy A1c generally?", "What is a typical resting heart rate?"]
    # The full set (incl. bare definitional, which route to general via openers) —
    # NONE may classify as a personal fact.
    EXTERNAL_ALL = EXTERNAL_FRAMED + ["What is diabetes?", "What does BMI mean?"]
    PERSONAL = ["What is my current weight?", "What's my last glucose reading?",
                "How is my health?", "Am I on track with my weight?"]

    def test_external_signal_detected(self):
        for q in self.EXTERNAL_FRAMED:
            self.assertTrue(external_general_signal(q), q)

    def test_personal_grounding_not_flagged_external(self):
        for q in self.PERSONAL:
            self.assertFalse(external_general_signal(q), q)

    def test_external_questions_suppress_personal_retrieval(self):
        # the foundational classifier must NOT claim an external question, even when
        # it contains a domain word ("weight", "blood pressure").
        for q in self.EXTERNAL_ALL:
            self.assertIsNone(classify_foundational_fact(q),
                              f"{q!r} wrongly classified as a personal fact")

    def test_personal_questions_still_retrieve(self):
        self.assertEqual(classify_foundational_fact("What is my current weight?"),
                         "current_weight")


class BoundaryRenderedResponseTests(TestCase):
    """End-to-end: an external weight question must not render personal weight."""
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p26bnd@x.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def test_healthy_weight_generally_does_not_leak_personal(self):
        with mock.patch(_CALL, side_effect=RuntimeError("down")), \
             mock.patch(_CALLT, side_effect=RuntimeError("down")):
            res = route_message(self.u, "What is a healthy weight generally?", None)
        # routed to the general lane (not foundational personal retrieval)
        self.assertEqual(res["lane"], "general_conversation")
        low = (res["answer"] or "").lower()
        for leak in ("your current weight", "your weight is"):
            self.assertNotIn(leak, low)
