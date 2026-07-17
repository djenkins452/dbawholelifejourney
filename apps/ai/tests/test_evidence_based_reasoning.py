# ==============================================================================
# File: apps/ai/tests/test_evidence_based_reasoning.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt makes the Chief of Staff EARN
#   recommendations — observation → retrieve related evidence (cross-domain) →
#   evaluate contributors → name uncertainty → explain reasoning → recommend only
#   when supported; never jump observation→recommendation, never invent a cause.
#   WLJ still only retrieves; OpenAI reasons. Deterministic prompt-contract only.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION, truth_tools


class EvidenceBasedRecommendationContractTests(TestCase):
    def test_recommendation_is_a_reasoning_intent_not_retrieval(self):
        low = CONSTITUTION.lower()
        self.assertIn("what should i do about x", low)
        self.assertIn("recommendation request", low)
        # reasoning intents deliver a recommendation, not a bare retrieval
        self.assertIn("recommendation", low)

    def test_never_jump_from_observation_to_recommendation(self):
        low = CONSTITUTION.lower()
        self.assertIn("never jump from an observation straight to a fix", low)
        self.assertIn("do not leap to a recommendation", low)
        self.assertIn("investigate first, then reason, then recommend", low)

    def test_evidence_chain_is_specified(self):
        low = CONSTITUTION.lower()
        for step in ("observation", "retrieve the related evidence",
                     "evaluate the likely contributors", "uncertainty",
                     "explain the reasoning"):
            self.assertIn(step, low)
        # prefer fixing contributors before changing the goal
        self.assertIn("before changing the goal", low)

    def test_cross_domain_investigation(self):
        low = CONSTITUTION.lower()
        self.assertIn("across domains", low)
        for domain in ("nutrition", "activity/cardio", "sleep", "body composition",
                       "recovery", "medication", "stress"):
            self.assertIn(domain, low)

    def test_recommendations_are_traceable_to_retrieved_facts(self):
        low = CONSTITUTION.lower()
        self.assertIn("traceable", low)
        self.assertIn("what you considered, what mattered, what didn't", low)
        self.assertIn("cannot trace back to the facts", low)

    def test_uncertainty_acknowledged_when_evidence_insufficient(self):
        low = CONSTITUTION.lower()
        self.assertIn("does not support a clear conclusion", low)
        self.assertIn("observing a little longer", low)

    def test_never_invents_evidence_or_causation(self):
        low = CONSTITUTION.lower()
        self.assertIn("never fabricate a cause or a causal relationship", low)
        self.assertIn("you never invent evidence", low)
        self.assertIn("wlj never invents it for you", low)

    def test_directive_reaches_the_assembled_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="ebr@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("EVIDENCE-BASED RECOMMENDATIONS", prompt)

    def test_no_deterministic_architecture_change_tool_set_unchanged(self):
        # Prompt-only: no analysis engine, no trends provider, no new/removed tool.
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history",
            "get_entity", "get_analysis", "get_user_truth", "get_foundational_health_facts",
        })
