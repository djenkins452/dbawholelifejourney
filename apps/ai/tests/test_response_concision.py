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


class CompletionSalienceContractTests(TestCase):
    """The compact completion reminder is placed at the HIGH-SALIENCE end of the assembled
    prompt and gives completion precedence over the standing relationship-warmth signals —
    without any output post-processing."""

    def _prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="sal@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        return svc._system_prompt({"current_context": {}})

    def test_reminder_is_at_the_high_salience_end_of_the_prompt(self):
        p = self._prompt()
        self.assertIn("RESPONSE COMPLETION (highest priority", p)
        # it comes AFTER the structured context (recency = highest salience)...
        self.assertGreater(p.index("RESPONSE COMPLETION (highest priority"),
                           p.index("STRUCTURED CONTEXT"))
        # ...and is near the very end (the last instruction before the user turn)
        self.assertLess(len(p) - p.index("RESPONSE COMPLETION (highest priority"), 1400)

    def test_short_factual_answer_is_complete_and_not_impolite(self):
        low = self._prompt().lower()
        self.assertIn("a short factual answer is complete", low)
        self.assertIn("not impolite", low)
        self.assertIn("brevity is not rudeness", low)

    def test_completion_overrides_relationship_warmth_and_question_frequency(self):
        low = self._prompt().lower()
        self.assertIn("override", low)
        for signal in ("supportive tone", "coaching style", "accountability style",
                       "question-frequency"):
            self.assertIn(signal, low)

    def test_question_frequency_does_not_require_a_follow_up(self):
        low = self._prompt().lower()
        self.assertIn("does not mean append a question", low)
        self.assertIn("may ask a genuinely useful question", low)

    def test_meaningful_follow_up_remains_optional(self):
        low = self._prompt().lower()
        self.assertIn("would you like me to list them?", low)
        self.assertIn("optional", low)

    def test_no_output_post_processing_answer_returned_verbatim(self):
        # Proves the correction is a PROMPT reminder, not an output post-processor:
        # generate() returns the model's answer byte-for-byte, even one WITH a trailing
        # invitation — nothing strips or rewrites it.
        from apps.ai.model_interface.service import ModelInterfaceService
        from apps.ai.models import AssistantConversation
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="npp@test.com", password="x")
        conv = AssistantConversation.get_or_create_active(user)
        canned = "You completed 5 workouts last week. If you need anything else, just ask."

        class _FakeAI:
            def _call_api_with_tools(self, system_prompt, user_message, **kw):
                return canned

        svc = ModelInterfaceService(user, ai_service=_FakeAI())
        result = svc.generate(conv, "how many workouts last week?", surface="chat")
        self.assertEqual(result["answer"], canned)   # verbatim — no stripping, no rewrite
