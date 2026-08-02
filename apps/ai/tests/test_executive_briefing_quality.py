# ==============================================================================
# File: apps/ai/tests/test_executive_briefing_quality.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Product-polish contract for the Model Interface governing prompt —
#   investigator-grade reasoning QUALITY and premium executive presentation:
#   (1) time-aware reasoning (what changed / when) BEFORE hypotheses,
#   (2) meaningful noticing (an overturned expectation that redirects the
#   investigation), (3) active disconfirmation before recommending, (4) executive
#   briefing formatting — no markdown headings / rules / dash lists, real "•"
#   bullets, (5) no generic fallback recommendations. Prompt-contract only; no
#   live-model assertions. Truth Resolution / Evidence surface unchanged.
# ==============================================================================
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.ai.model_interface.constitution import CONSTITUTION, truth_tools


class TimeAwareReasoningTests(TestCase):
    def test_investigates_change_over_time_before_hypotheses(self):
        low = CONSTITUTION.lower()
        self.assertIn("first, investigate change over time", low)
        self.assertIn("chronologically", low)
        self.assertIn("what changed recently", low)
        self.assertIn("before or after", low)

    def test_a_current_value_is_not_a_cause(self):
        low = CONSTITUTION.lower()
        self.assertIn("a current value is not a cause", low)
        # a long-standing condition cannot explain a recent change
        self.assertIn("cannot by itself explain a recent change", low)
        # the concrete protein-snapshot correction
        self.assertIn("predates the slowdown", low)


class MeaningfulNoticingTests(TestCase):
    def test_notice_not_restate_with_the_shift_example(self):
        low = CONSTITUTION.lower()
        self.assertIn("do not merely restate", low)
        self.assertIn("restating a number is not noticing", low)
        self.assertIn("i expected workouts to be the limiting factor", low)
        self.assertIn("shifted my investigation toward", low)


class ActiveDisconfirmationTests(TestCase):
    def test_challenge_asks_the_three_disconfirming_questions(self):
        low = CONSTITUTION.lower()
        self.assertIn("before any recommendation", low)
        self.assertIn("what else could explain this", low)
        self.assertIn("what evidence weakens my current hypothesis", low)
        self.assertIn("what would i expect to see if this hypothesis were wrong", low)


class NoGenericFallbackTests(TestCase):
    def test_names_the_banned_generic_recommendations(self):
        low = CONSTITUTION.lower()
        for banned in ("introduce more variety", "monitor your calories", "keep exercising"):
            self.assertIn(banned, low)

    def test_requires_survival_rejection_and_evidence(self):
        low = CONSTITUTION.lower()
        self.assertIn("why it survived the investigation", low)
        self.assertIn("why the competing explanations were rejected", low)
        self.assertIn("evidence for and against", low)

    def test_product_standard_language(self):
        low = CONSTITUTION.lower()
        self.assertIn("i hadn't noticed that", low)
        self.assertIn("i already knew that", low)


class ExecutiveFormattingTests(TestCase):
    def test_section_names_the_executive_briefing_standard(self):
        low = CONSTITUTION.lower()
        self.assertIn("executive briefing voice", low)
        self.assertIn("not a documentation generator", low)

    def test_prohibits_markdown_headings_rules_and_dash_lists(self):
        # The forbidden tokens are named literally so the rule is unambiguous.
        self.assertIn("'###'", CONSTITUTION)
        self.assertIn("'---'", CONSTITUTION)
        self.assertIn("'- '", CONSTITUTION)   # markdown dash bullet
        low = CONSTITUTION.lower()
        self.assertIn("do not use markdown heading syntax", low)

    def test_requires_real_bullet_character(self):
        self.assertIn("•", CONSTITUTION)      # the actual bullet char to use
        low = CONSTITUTION.lower()
        self.assertIn("real bullet character", low)

    def test_bold_only_when_it_aids_scanning(self):
        low = CONSTITUTION.lower()
        self.assertIn("use bold only", low)
        self.assertIn("never decoratively", low)

    def test_short_answers_stay_prose(self):
        low = CONSTITUTION.lower()
        self.assertIn("keep short answers as natural prose", low)
        self.assertIn("never impose a", low)


class UnchangedSurfaceTests(TestCase):
    def test_truth_resolution_tool_set_unchanged(self):
        # Prompt-only polish: no truth surface added/removed.
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history", "get_readings",
            "get_event_frequency", "get_comparison", "get_adherence", "get_entity",
            "get_analysis", "get_user_truth", "get_foundational_health_facts",
        })

    def test_polish_reaches_the_assembled_prompt(self):
        user = get_user_model().objects.create_user(email="ebq@test.com", password="x")
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(user, ai_service=object())
        low = svc._system_prompt({"current_context": {}}).lower()
        self.assertIn("first, investigate change over time", low)
        self.assertIn("executive briefing voice", low)
