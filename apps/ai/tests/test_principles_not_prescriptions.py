# ==============================================================================
# File: apps/ai/tests/test_principles_not_prescriptions.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt keeps the Chief of Staff a
#   strategic advisor — it recommends PRINCIPLES (attributed industry guidance
#   related to the user's data), not PRESCRIPTIONS (specific personal directives).
#   It draws the line truth → evidence → personal decision, stays goal-aware, and
#   is causation-careful. Deterministic prompt-contract only; no live-model asserts.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION, truth_tools


class PrinciplesNotPrescriptionsContractTests(TestCase):
    def test_advisor_not_a_specialized_professional(self):
        low = CONSTITUTION.lower()
        self.assertIn("principles, not prescriptions", low)
        self.assertIn("never the user's physician, personal trainer, dietitian, "
                      "financial advisor, or therapist", low)
        self.assertIn("do not issue a specific personal directive", low)

    def test_prescriptive_directives_named_as_what_to_avoid(self):
        low = CONSTITUTION.lower()
        for directive in ("increase your squat weight", "eat less rice",
                          "do more cardio", "sleep more"):
            self.assertIn(directive, low)

    def test_attributed_industry_guidance_related_to_user_data(self):
        low = CONSTITUTION.lower()
        self.assertIn("attributed whenever practical", low)
        self.assertIn("150 minutes", low)
        self.assertIn("hours of sleep", low)
        self.assertIn("progressive-overload", low)
        self.assertIn("relate that guidance to the user's own data", low)

    def test_three_tier_line_user_owns_the_decision(self):
        low = CONSTITUTION.lower()
        self.assertIn("evidence-based industry guidance", low)
        self.assertIn("personal decision", low)
        self.assertIn("you connect the first two", low)
        self.assertIn("owns the third", low)

    def test_causation_care(self):
        low = CONSTITUTION.lower()
        self.assertIn("this may be contributing", low)
        self.assertIn("one possible explanation", low)
        self.assertIn("distinguish correlation from causation", low)

    def test_goal_aware(self):
        low = CONSTITUTION.lower()
        self.assertIn("do not assume bodybuilding", low)
        self.assertIn("unless it is explicitly established", low)
        self.assertIn("not elite athletic training", low)

    def test_medical_policy_still_governs(self):
        low = CONSTITUTION.lower()
        self.assertIn("individualized treatment decisions remain with qualified "
                      "healthcare professionals", low)

    def test_reaches_the_assembled_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="pnp@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("PRINCIPLES, NOT PRESCRIPTIONS", prompt)

    def test_no_deterministic_architecture_change_tool_set_unchanged(self):
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history",
            "get_entity", "get_foundational_health_facts",
        })
