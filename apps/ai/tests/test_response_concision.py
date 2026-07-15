# ==============================================================================
# File: apps/ai/tests/test_response_concision.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt (CONSTITUTION) instructs the
#   model to answer and stop — no generic invitation filler by default, one
#   concise follow-up only when it advances the objective. Deterministic contract
#   only (the prompt carries the rule); no brittle live-model wording assertions.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION


class ResponseConcisionContractTests(TestCase):
    def test_constitution_has_a_concision_directive(self):
        self.assertIn("CONCISION", CONSTITUTION)
        low = CONSTITUTION.lower()
        self.assertIn("answer the question", low)
        self.assertIn("fewest necessary words", low)

    def test_constitution_names_the_banned_filler_phrases(self):
        low = CONSTITUTION.lower()
        for phrase in ("if there's anything else", "feel free to ask",
                       "let me know if", "if you need anything else"):
            self.assertIn(phrase, low)
        # framed as a rare exception, not a default close
        self.assertIn("rare", low)

    def test_constitution_allows_exactly_one_meaningful_follow_up(self):
        low = CONSTITUTION.lower()
        self.assertIn("exactly one", low)
        self.assertIn("advances the current objective", low)
        self.assertIn("no meaningful next step", low)

    def test_system_prompt_carries_the_rule(self):
        # The rule must survive into the actual system prompt the model receives.
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="cc@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("CONCISION", prompt)
