# ==============================================================================
# File: apps/ai/tests/test_competing_hypotheses.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt requires INVESTIGATOR-grade
#   reasoning on analytical questions — generate MULTIPLE competing hypotheses,
#   weigh evidence FOR and AGAINST each, state confidence + uncertainty, CHALLENGE
#   the leading hypothesis, RANK/prioritize, and never force a winner — rather than
#   stopping at the first plausible explanation. Reasoning stays entirely in the
#   model; WLJ only supplies deterministic evidence. Deterministic prompt-contract
#   only; no live-model assertions.
# ==============================================================================
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.ai.model_interface.constitution import (
    CONSTITUTION, RESPONSE_COMPLETION_REMINDER, truth_tools,
)


class CompetingHypothesesContractTests(TestCase):
    def test_names_the_section_and_the_investigator_stance(self):
        low = CONSTITUTION.lower()
        self.assertIn("reason across competing hypotheses", low)
        self.assertIn("think like an", low)
        self.assertIn("investigator", low)
        # the anti-pattern is explicitly rejected
        self.assertIn("find one plausible explanation", low)

    def test_requires_multiple_competing_hypotheses(self):
        low = CONSTITUTION.lower()
        self.assertIn("generate multiple competing hypotheses", low)
        self.assertIn("one hypothesis is never enough", low)

    def test_requires_evidence_for_against_confidence_uncertainty(self):
        low = CONSTITUTION.lower()
        self.assertIn("evidence for it", low)
        self.assertIn("evidence against it", low)
        self.assertIn("confidence", low)
        self.assertIn("remaining uncertainty", low)

    def test_requires_challenging_the_leading_hypothesis(self):
        low = CONSTITUTION.lower()
        self.assertIn("challenge your leading hypothesis", low)
        self.assertIn("what evidence argues against this", low)
        self.assertIn("stronger", low)
        self.assertIn("more uncertain", low)

    def test_requires_ranking_and_prioritization(self):
        low = CONSTITUTION.lower()
        self.assertIn("rank the hypotheses", low)
        self.assertIn("prioritize", low)

    def test_does_not_force_a_winner(self):
        low = CONSTITUTION.lower()
        self.assertIn("do not force a winner", low)
        self.assertIn("equally plausible", low)
        self.assertIn("manufacture certainty", low)

    def test_surfaces_investigator_signals(self):
        low = CONSTITUTION.lower()
        for signal in ("surprised", "concerns", "confidence",
                       "does not fit", "assumptions"):
            self.assertIn(signal, low)

    def test_no_generic_fallback_recommendations(self):
        low = CONSTITUTION.lower()
        self.assertIn("no generic fallback", low)
        # the weak vs strong contrast is present as concrete guidance
        self.assertIn("increase protein", low)
        self.assertIn("more mixed", low)
        self.assertIn("that judgment is the product", low)

    def test_reasoning_only_from_deterministic_evidence(self):
        low = CONSTITUTION.lower()
        # hypotheses are investigated with WLJ truth tools, never fabricated evidence
        self.assertIn("investigate each with deterministic wlj evidence", low)
        self.assertIn("never invent evidence to prop up or dismiss one", low)

    def test_completion_reminder_protects_the_multihypothesis_reasoning(self):
        # The high-salience tail must not let completion collapse the analysis to one guess.
        low = RESPONSE_COMPLETION_REMINDER.lower()
        self.assertIn("do not collapse the analysis to the first plausible explanation", low)
        self.assertIn("competing hypotheses", low)

    def test_reminder_reaches_the_assembled_prompt(self):
        user = get_user_model().objects.create_user(email="hyp@test.com", password="x")
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(user, ai_service=object())
        low = svc._system_prompt({"current_context": {}}).lower()
        self.assertIn("reason across competing hypotheses", low)
        self.assertIn("do not collapse the analysis to the first plausible explanation", low)

    def test_truth_resolution_tool_set_unchanged(self):
        # Prompt-only change: no truth surface added/removed.
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history",
            "get_entity", "get_analysis", "get_foundational_health_facts",
        })
