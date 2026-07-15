# ==============================================================================
# File: apps/ai/tests/test_response_concision.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt (CONSTITUTION) instructs the
#   model to answer and stop — generic invitation filler is PROHIBITED, and a
#   follow-up is offered only when all four value conditions hold (and is always
#   optional). Deterministic contract only (the prompt carries the rule); no
#   brittle live-model wording assertions.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION


class ResponseConcisionContractTests(TestCase):
    def test_constitution_has_a_concision_directive(self):
        self.assertIn("CONCISION", CONSTITUTION)
        low = CONSTITUTION.lower()
        self.assertIn("answer the question", low)
        self.assertIn("fewest necessary words", low)
        self.assertIn("elite executive assistant", low)

    def test_generic_invitation_filler_is_prohibited(self):
        low = CONSTITUTION.lower()
        self.assertIn("never end a response with a generic invitation", low)
        self.assertIn("prohibited", low)
        self.assertIn("filler", low)
        for phrase in ("if you need more details", "if there's anything else",
                       "feel free to ask", "let me know if",
                       "if you have any more questions", "anything else i can help with"):
            self.assertIn(phrase, low)

    def test_follow_up_requires_all_four_conditions_and_is_optional(self):
        low = CONSTITUTION.lower()
        self.assertIn("only when all of these are true", low)
        self.assertIn("directly related", low)                     # (1)
        self.assertIn("immediately from deterministic truth", low)  # (2)
        self.assertIn("materially advances", low)                   # (3)
        self.assertIn("more valuable than simply ending", low)      # (4)
        self.assertIn("exactly one", low)
        # optional, never required — and if any condition fails, stop
        self.assertIn("optional, never required", low)
        self.assertIn("if any of those four is false", low)

    def test_signal_not_conversation_length(self):
        low = CONSTITUTION.lower()
        self.assertIn("signal, not conversation length", low)
        self.assertIn("must justify its existence", low)

    def test_system_prompt_carries_the_rule(self):
        # The rule must survive into the actual system prompt the model receives.
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="cc@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("CONCISION", prompt)
        self.assertIn("PROHIBITED", prompt)
