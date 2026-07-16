# ==============================================================================
# File: apps/ai/tests/test_investigate_before_concluding.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt teaches the Chief of Staff to
#   INVESTIGATE before concluding on analytical requests — the first retrieval is
#   never assumed sufficient. Before reporting "insufficient data" the model must
#   establish that WLJ genuinely holds no more relevant truth (a real absence),
#   distinct from "I have not yet gathered enough of the truth WLJ does hold"
#   (keep investigating). WLJ still only retrieves; OpenAI performs the
#   investigation and reasoning. Truth Resolution / providers unchanged.
#   Deterministic prompt-contract only; no live-model assertions.
# ==============================================================================
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.ai.model_interface.constitution import (
    CONSTITUTION, RESPONSE_COMPLETION_REMINDER, truth_tools,
)


class InvestigateBeforeConcludingContractTests(TestCase):
    def test_analytical_requests_trigger_investigation_not_query_engine(self):
        low = CONSTITUTION.lower()
        self.assertIn("investigate before concluding", low)
        self.assertIn("the first retrieval is never", low)
        self.assertIn("investigator, not a query engine", low)
        # the explicit anti-pattern is named and rejected
        self.assertIn("question → one retrieval → conclusion", low)

    def test_first_retrieval_is_not_grounds_for_insufficient(self):
        low = CONSTITUTION.lower()
        self.assertIn("is not a basis to conclude 'insufficient data'", low)
        self.assertIn("keep investigating", low)

    def test_before_insufficient_must_establish_no_more_truth_exists(self):
        low = CONSTITUTION.lower()
        # the two-part gate before concluding insufficiency
        self.assertIn("wlj genuinely holds no more relevant deterministic truth", low)
        self.assertIn("would not materially improve the answer", low)

    def test_investigation_may_retrieve_multiple_truth_surfaces(self):
        low = CONSTITUTION.lower()
        # history across more than one window + record detail + progression
        self.assertIn("more than one window", low)
        self.assertIn("get_history", low)
        self.assertIn("get_entity", low)
        self.assertIn("progression", low)

    def test_distinguishes_genuine_absence_from_undergathered(self):
        low = CONSTITUTION.lower()
        self.assertIn("wlj holds no such data", low)               # genuine absence
        self.assertIn("i have not yet gathered enough", low)       # keep investigating
        self.assertIn("all available truth", low)

    def test_investigation_is_purposeful_not_endless_and_never_invents(self):
        low = CONSTITUTION.lower()
        self.assertIn("purposeful, not endless", low)
        self.assertIn("do not retrieve forever", low)
        self.assertIn("never invent evidence", low)

    def test_principle_is_general_not_workout_specific(self):
        low = CONSTITUTION.lower()
        self.assertIn("this is not workout-specific", low)
        # spans multiple analytical domains
        for domain in ("weight", "nutrition", "finance", "sleep", "goals"):
            self.assertIn(domain, low)

    def test_workout_example_is_present(self):
        low = CONSTITUTION.lower()
        self.assertIn("analyze my workout trends", low)
        self.assertIn("get_analysis('health', 'workouts')", low)

    def test_high_salience_reminder_guards_premature_insufficient(self):
        # The completion reminder is assembled LAST (highest salience); it must not let the
        # model cut analysis short by declaring insufficiency after one retrieval.
        low = RESPONSE_COMPLETION_REMINDER.lower()
        self.assertIn("investigate before concluding", low)
        self.assertIn("never report 'insufficient", low)
        self.assertIn("one tool call", low)

    def test_reminder_reaches_the_assembled_prompt(self):
        user = get_user_model().objects.create_user(email="ibc@test.com", password="x")
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(user, ai_service=object())
        low = svc._system_prompt({"current_context": {}}).lower()
        self.assertIn("investigate before concluding", low)
        self.assertIn("reserve it for a genuine absence", low)

    def test_analysis_surface_is_the_investigation_guarantee(self):
        # The behavioral contract is now backed by a deterministic surface, not only a
        # prompt: get_analysis composes the whole investigation in one call.
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertIn("get_analysis", names)
        low = CONSTITUTION.lower()
        self.assertIn("get_analysis", low)
        self.assertIn("holds_data", low)

    def test_understanding_is_not_a_completeness_authority(self):
        # Resolves the override tension: the whole-life summary never justifies an
        # "insufficient" verdict on a specific analytical subject.
        low = CONSTITUTION.lower()
        self.assertIn("whole-life summary", low)
        self.assertIn("never conclude 'insufficient' for the subject", low)

    def test_truth_resolution_tool_set_is_the_expected_six(self):
        # Analysis added as a first-class truth surface (state/history/entity/analysis).
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history",
            "get_entity", "get_analysis", "get_foundational_health_facts",
        })
