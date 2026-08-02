# ==============================================================================
# File: apps/ai/tests/test_intent_retrieve_reason.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt distinguishes RETRIEVAL intent
#   (the deterministic value is the answer) from REASONING intent (analyze /
#   compare / summarize / interpret / trends / evaluate → retrieve THEN reason
#   THEN answer the analysis). WLJ still only retrieves; OpenAI reasons over the
#   supplied truth. Deterministic prompt-contract only; no live-model assertions.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION, truth_tools


class IntentRetrieveVsReasonContractTests(TestCase):
    def test_prompt_distinguishes_retrieval_from_reasoning(self):
        low = CONSTITUTION.lower()
        self.assertIn("retrieve vs reason", low)
        self.assertIn("the deterministic truth is the answer", low)   # RETRIEVAL bullet
        self.assertIn("precondition, not the answer", low)            # REASONING bullet

    def test_reasoning_intents_named_and_require_retrieve_then_reason(self):
        low = CONSTITUTION.lower()
        for verb in ("analyze", "compare", "summarize", "interpret", "evaluate my progress"):
            self.assertIn(verb, low)
        self.assertIn("patterns or trends", low)
        self.assertIn("then reason over it", low)
        self.assertIn("deliver the requested analysis", low)
        self.assertIn("do not stop after retrieval", low)

    def test_retrieval_intents_stay_terse(self):
        low = CONSTITUTION.lower()
        self.assertIn("how many", low)
        self.assertIn("list", low)
        self.assertIn("return it plainly and stop", low)

    def test_boundary_reason_over_truth_never_invent(self):
        low = CONSTITUTION.lower()
        self.assertIn("you interpret truth; you never invent it", low)

    def test_completion_reminder_reconciles_analysis_is_not_bare_retrieval(self):
        # Assembled at the high-salience prompt tail — completion must not cut off reasoning.
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="irr@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        low = svc._system_prompt({"current_context": {}}).lower()
        self.assertIn("not satisfied by a bare retrieved count or list", low)
        self.assertIn("its objective is the reasoning", low)
        self.assertIn("deliver the analysis", low)
        # and the intent directive itself reaches the prompt
        self.assertIn("retrieve vs reason", low)

    def test_truth_resolution_tool_set_unchanged(self):
        # Prompt-only change: no tool added/removed, no retrieval surface touched.
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history", "get_readings",
            "get_event_frequency", "get_comparison", "get_adherence", "get_entity",
            "get_analysis", "get_user_truth", "get_foundational_health_facts",
        })
