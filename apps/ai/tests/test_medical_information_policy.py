# ==============================================================================
# File: apps/ai/tests/test_medical_information_policy.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt (CONSTITUTION) carries the
#   permanent Medical Information Policy — WLJ interprets deterministic health
#   truth and explains established medical knowledge, but never diagnoses,
#   prescribes, or gives personalized medical advice. Deterministic contract
#   only (the prompt carries the rule); no brittle live-model wording assertions.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION


class MedicalInformationPolicyContractTests(TestCase):
    def test_policy_section_present_and_non_clinician(self):
        self.assertIn("MEDICAL INFORMATION POLICY", CONSTITUTION)
        low = CONSTITUTION.lower()
        self.assertIn("not the", low)
        self.assertIn("healthcare provider", low)
        for verb in ("never diagnose", "never prescribe"):
            self.assertIn(verb, low)
        # never directs the user to change meds themselves
        self.assertIn("start, stop, increase, or decrease", low)

    def test_three_levels_are_defined(self):
        low = CONSTITUTION.lower()
        self.assertIn("level 1", low)
        self.assertIn("level 2", low)
        self.assertIn("level 3", low)
        # L1 = answer directly, no disclaimer; L2 = attribute; L3 = defer
        self.assertIn("no disclaimer needed", low)
        self.assertIn("attribute", low)

    def test_level2_names_authoritative_sources(self):
        # At least the canonical bodies must be advertised as attribution anchors.
        for org in ("american diabetes association", "cdc", "nih", "who", "fda", "ada"):
            self.assertIn(org, CONSTITUTION.lower())

    def test_level3_defers_to_healthcare_professional_not_boilerplate(self):
        low = CONSTITUTION.lower()
        self.assertIn("should i", low)                       # recognizes the decision question
        self.assertIn("healthcare professional", low)        # deferral target
        self.assertIn("do not give personalized medical advice", low)
        self.assertIn("non-boilerplate", low)                # natural, not repeated disclaimers

    def test_truth_vs_guidance_never_blurred(self):
        low = CONSTITUTION.lower()
        self.assertIn("never blur", low)
        self.assertIn("interpreter", low)                    # the goal framing
        self.assertIn("explainer", low)

    def test_policy_survives_into_the_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="mip@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("MEDICAL INFORMATION POLICY", prompt)
