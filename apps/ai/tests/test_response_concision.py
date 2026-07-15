# ==============================================================================
# File: apps/ai/tests/test_response_concision.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt (CONSTITUTION) defines response
#   COMPLETION — a response ends when the user's objective is satisfied — rather
#   than blacklisting filler phrases (which the model just paraphrases around). A
#   follow-up is optional and gated by three value conditions. Deterministic
#   contract only; no brittle live-model wording assertions.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION


class ResponseCompletionContractTests(TestCase):
    def test_defines_completion_by_objective_satisfied(self):
        self.assertIn("COMPLETION", CONSTITUTION)
        low = CONSTITUTION.lower()
        self.assertIn("a response is complete the moment", low)
        self.assertIn("objective has been satisfied", low)
        self.assertIn("the response ends", low)
        self.assertIn("elite executive assistant", low)

    def test_teaches_completion_not_a_phrase_blacklist(self):
        # The governing rule is principle-based: the test is the objective, not banned
        # words — and rewording a trailing offer does not satisfy it (END, don't rephrase).
        low = CONSTITUTION.lower()
        self.assertIn("the test is not which words to avoid", low)
        self.assertIn("whether the objective is met", low)
        self.assertIn("the fix is to end, not to rephrase", low)

    def test_follow_up_is_optional_and_gated_by_three_conditions(self):
        low = CONSTITUTION.lower()
        self.assertIn("never expected, never required", low)
        self.assertIn("only when all of these are true", low)
        self.assertIn("directly advances the user's current objective", low)   # (1)
        self.assertIn("immediately from deterministic truth", low)             # (2)
        self.assertIn("significantly more value", low)                         # (3)
        self.assertIn("if any one is false, end the response immediately", low)

    def test_completion_rule_survives_into_the_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="comp@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("COMPLETION", prompt)
        self.assertIn("objective is satisfied", prompt.lower())
