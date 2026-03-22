"""
CoS Truth Enforcement Tests — Validates that Beth's prompt and validator
prevent fabricated completions.

These tests simulate real user scenarios with a known execution state
(nothing completed) and verify:
1. The assembled prompt contains FACTS block with correct values
2. The assembled prompt contains FINAL TRUTH ANCHOR
3. The post-generation validator catches fabricated responses
4. The post-generation validator passes clean responses

These tests do NOT call the LLM — they test the prompt structure and
validator logic, which are the system-enforceable layers.
"""
import re
from datetime import date
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

User = get_user_model()


class CosTruthPromptStructureTest(TestCase):
    """Verify the prompt Beth receives has correct truth enforcement."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='cos_truth_test@test.com',
            password='testpass123',
        )
        # Set up required user state
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def _build_cos_injection(self):
        """Build the CoS injection string for our test user."""
        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        return format_cos_system_injection(context)

    def test_facts_block_at_top(self):
        """FACTS block must be the first section in the prompt."""
        injection = self._build_cos_injection()
        facts_pos = injection.find('FACTS — AUTHORITATIVE')
        self.assertGreater(facts_pos, -1, "FACTS block not found in prompt")
        # Must be in the first 200 chars
        self.assertLess(
            facts_pos, 200,
            f"FACTS block at position {facts_pos} — should be near top"
        )

    def test_facts_show_not_done(self):
        """With no completions, all FACTS must show NO."""
        injection = self._build_cos_injection()
        self.assertIn('prayer_completed_today: NO', injection)
        self.assertIn('bible_reading_completed_today: NO', injection)
        self.assertIn('workout_completed_today: NO', injection)
        self.assertIn('journal_completed_today: NO', injection)

    def test_facts_rules_present(self):
        """FACTS section must contain enforcement rules."""
        injection = self._build_cos_injection()
        self.assertIn(
            'MUST NOT say it is done, complete, or finished',
            injection,
        )
        self.assertIn(
            'NOTHING in the PATTERNS section below can override',
            injection,
        )

    def test_patterns_labeled_advisory(self):
        """Pattern/signal sections must be labeled as advisory."""
        injection = self._build_cos_injection()
        self.assertIn(
            'PATTERNS & SIGNALS (advisory',
            injection,
        )

    def test_final_truth_anchor_present(self):
        """FINAL TRUTH ANCHOR must be at the end of the prompt."""
        injection = self._build_cos_injection()
        anchor_pos = injection.find('FINAL EXECUTION STATUS')
        self.assertGreater(
            anchor_pos, -1,
            "FINAL TRUTH ANCHOR not found in prompt"
        )
        # Must be in the last 20% of the prompt
        total_len = len(injection)
        self.assertGreater(
            anchor_pos / total_len, 0.8,
            f"FINAL TRUTH ANCHOR at {anchor_pos/total_len:.0%} — "
            f"should be near end"
        )

    def test_facts_before_patterns(self):
        """FACTS must appear before PATTERNS in the prompt."""
        injection = self._build_cos_injection()
        facts_pos = injection.find('FACTS — AUTHORITATIVE')
        patterns_pos = injection.find('PATTERNS & SIGNALS')
        self.assertGreater(facts_pos, -1)
        self.assertGreater(patterns_pos, -1)
        self.assertLess(
            facts_pos, patterns_pos,
            "FACTS must come before PATTERNS in prompt"
        )

    def test_no_streak_data_in_prompt(self):
        """Reading streak data must NOT appear in the CoS prompt."""
        injection = self._build_cos_injection()
        # Should not contain "Reading streak: X days" format
        self.assertNotRegex(
            injection,
            r'Reading streak: \d+ days(?!\s*—\s*streak is HISTORICAL)',
            "Raw streak data found in prompt without disclaimer"
        )


class CosTruthValidatorTest(TestCase):
    """Verify the post-generation validator catches fabricated responses."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='cos_validator_test@test.com',
            password='testpass123',
        )
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _mock_execution(self):
        """Mock execution data: nothing completed today."""
        return {
            'summaries': {
                'domains': {
                    'prayer': False,
                    'bible_reading': False,
                    'workout': False,
                    'journal': False,
                    'faith_engaged': False,
                },
                'routines': {},
                'medications': {},
                'tasks_completed_today': 0,
            }
        }

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_1_fabricated_completion_rejected(self, mock_exec):
        """TEST CASE 1: Response claiming prayer is done must be rejected."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        bad_response = (
            "Great start to your morning! Your prayer and Bible reading "
            "have been completed. Now let's focus on your workout."
        )
        result, violations = validate_response_truth(
            bad_response, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED a fabricated response: {bad_response}"
        )
        domains = [v['domain'] for v in violations]
        self.assertIn('prayer', domains)
        self.assertIn('bible_reading', domains)

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_2_false_praise_rejected(self, mock_exec):
        """TEST CASE 2: 'Great start' with nothing done must be rejected."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        bad_response = (
            "You're off to a great start this morning! Keep the momentum "
            "going."
        )
        result, violations = validate_response_truth(
            bad_response, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED false praise: {bad_response}"
        )

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_3_honest_response_passes(self, mock_exec):
        """TEST CASE 3: Honest 'nothing done' response must PASS."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        good_response = (
            "Nothing from your morning routine has been completed yet. "
            "Let's start with one item — prayer would be a good first step."
        )
        result, violations = validate_response_truth(
            good_response, self.user, allow_regenerate=True,
        )
        self.assertEqual(
            len(violations), 0,
            f"Validator REJECTED an honest response: {violations}"
        )

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_4_direct_no_answer_passes(self, mock_exec):
        """TEST CASE 4: Direct 'No' to completion question must PASS."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        good_response = (
            "No, neither prayer nor Bible reading are completed today. "
            "Would you like to start with prayer?"
        )
        result, violations = validate_response_truth(
            good_response, self.user, allow_regenerate=True,
        )
        self.assertEqual(
            len(violations), 0,
            f"Validator REJECTED an honest 'No' answer: {violations}"
        )

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_5_positive_reframe_without_lying_passes(self, mock_exec):
        """TEST CASE 5: Positive reframe without fabrication must PASS."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        good_response = (
            "Your morning routine hasn't started yet, but you've got the "
            "whole day ahead of you. The fact that you're checking in shows "
            "you're ready to move. Start with prayer — that sets the tone "
            "for everything else."
        )
        result, violations = validate_response_truth(
            good_response, self.user, allow_regenerate=True,
        )
        self.assertEqual(
            len(violations), 0,
            f"Validator REJECTED a positive-but-honest reframe: {violations}"
        )

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_6_strong_morning_rejected(self, mock_exec):
        """TEST CASE 6: 'Strong morning' with nothing done must be rejected."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        bad_response = (
            "Strong morning so far! You've been consistent this week."
        )
        result, violations = validate_response_truth(
            bad_response, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED 'strong morning' with nothing done: "
            f"{bad_response}"
        )

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_7_workout_done_claim_rejected(self, mock_exec):
        """TEST CASE 7: Claiming workout is done when not must be rejected."""
        mock_exec.return_value = self._mock_execution()
        from apps.ai.cos_truth_validator import validate_response_truth

        bad_response = (
            "Your workout is done for the day. Nice work getting that in "
            "early."
        )
        result, violations = validate_response_truth(
            bad_response, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED fabricated workout completion"
        )
        domains = [v['domain'] for v in violations]
        self.assertIn('workout', domains)

    @patch('apps.core.execution.today_execution.build_today_execution', autospec=True)
    def test_case_8_completed_domain_passes(self, mock_exec):
        """TEST CASE 8: Claiming done for actually-done domain must PASS."""
        exec_data = self._mock_execution()
        exec_data['summaries']['domains']['prayer'] = True
        mock_exec.return_value = exec_data
        from apps.ai.cos_truth_validator import validate_response_truth

        good_response = (
            "Prayer is done for the day. Bible reading is still pending — "
            "want to start that next?"
        )
        result, violations = validate_response_truth(
            good_response, self.user, allow_regenerate=True,
        )
        # Should NOT flag prayer (it IS done), should NOT flag bible
        # (response says "pending")
        prayer_violations = [
            v for v in violations if v['domain'] == 'prayer'
        ]
        self.assertEqual(
            len(prayer_violations), 0,
            "Validator wrongly flagged a truthful prayer completion claim"
        )
