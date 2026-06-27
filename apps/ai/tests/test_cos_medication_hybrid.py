# ==============================================================================
# File: apps/ai/tests/test_cos_medication_hybrid.py
# Description: Hybrid (personal + general education) routing. Personal med facts
#              come from WLJ; medication PURPOSES are general knowledge. The
#              deterministic foundational fast-path must DECLINE the hybrid so it
#              reaches the tool loop (which combines WLJ truth + general knowledge).
# ==============================================================================
"""
Regression: "which of my medications are commonly used for diabetes?" was claimed
by the foundational-facts lane (keyword 'medication' → current_medications), which
emits only the deterministic list — the educational layer never ran, and the
hybrid-capable tool loop was never reached.

Fix: the foundational classifier declines on an EDUCATIONAL OVERLAY, so the hybrid
falls through every single-source lane to the tool loop.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.foundational_facts import (
    answer_foundational_fact,
    classify_foundational_fact,
)

User = get_user_model()

SIMPLE = ["what medications do I take?", "list all my medications",
          "what meds am I on"]
HYBRID = ["which of my medications are commonly used for diabetes?",
          "list each medication and what it is commonly used for",
          "what are my medications used for?",
          "why am I taking each of these medications?"]


class FoundationalClassifierTests(TestCase):
    """Deterministic — no LLM, no DB."""

    def test_simple_medication_questions_are_claimed(self):
        for q in SIMPLE:
            self.assertEqual(classify_foundational_fact(q), "current_medications",
                             f"simple list question should stay on the fast path: {q!r}")

    def test_hybrid_education_questions_are_declined(self):
        for q in HYBRID:
            self.assertIsNone(classify_foundational_fact(q),
                              f"hybrid education question must decline → tool loop: {q!r}")

    def test_other_facts_unaffected(self):
        # The overlay only diverts genuine education questions; plain facts still route.
        self.assertEqual(classify_foundational_fact("what is my weight"), "current_weight")
        self.assertEqual(classify_foundational_fact("how much protein today"), "protein_today")


class HybridRoutingTests(TestCase):
    """route_message: the hybrid is claimed by NO single-source lane (→ tool loop)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="hybrid@example.com", password="x")

    def test_hybrid_falls_through_to_tool_loop(self):
        from apps.ai.chatgpt_cos.lanes import route_message
        # The only LLM lane that could claim a personal-pronoun question is the
        # reasoning planner; it declines non-reasoning questions in production.
        with mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                        return_value=None):
            for q in HYBRID:
                routed = route_message(self.user, q)
                self.assertIsNone(routed, f"hybrid must reach the tool loop: {q!r}")

    def test_simple_list_question_still_handled_by_a_lane(self):
        # The deterministic fast path still owns the plain list question (the
        # foundational lane claims it; it does not fall to the tool loop).
        self.assertEqual(classify_foundational_fact("list all my medications"),
                         "current_medications")
        # And the foundational lane DECLINES the hybrid (returns None → tool loop).
        self.assertIsNone(answer_foundational_fact(
            self.user, "which of my medications are commonly used for diabetes?"))


class HybridGenerateTests(TestCase):
    """End-to-end: the hybrid reaches the tool loop and combines WLJ + general
    knowledge into one answer — no emergency fallback."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="hybrid_gen@example.com",
                                            password="x", first_name="Danny")

    def test_hybrid_combines_personal_and_general_no_fallback(self):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        svc = ChatGPTCoSService(self.user)
        combined = ("Metformin is commonly used to help lower blood sugar in type 2 "
                    "diabetes. Based on what WLJ knows, you take Metformin alongside "
                    "Mounjaro, Humalog, and Lantus.")
        with mock.patch.object(ChatGPTCoSService, "_history", return_value=[]), \
             mock.patch("apps.core.ai_state.state_engine.get_user_state",
                        return_value={}), \
             mock.patch("apps.ai.cos_services.get_standing_context",
                        return_value={"status": "ready"}), \
             mock.patch("apps.ai.cos_services.get_tool_schemas", return_value=[]), \
             mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                        return_value=None), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        return_value=combined):
            result = svc.generate(
                object(), "which of my medications are commonly used for diabetes?")
        self.assertEqual(result["answer"], combined)
        self.assertIsNone(result["empty_reason"])
        self.assertNotIn("couldn't pull that together", result["answer"].lower())
