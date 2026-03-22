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

    def test_locked_facts_at_top(self):
        """LOCKED FACT STATEMENTS must be the first section in the prompt."""
        injection = self._build_cos_injection()
        facts_pos = injection.find('LOCKED FACT STATEMENTS')
        self.assertGreater(
            facts_pos, -1,
            "LOCKED FACT STATEMENTS not found in prompt",
        )
        self.assertLess(
            facts_pos, 200,
            f"LOCKED FACTS at position {facts_pos} — should be near top",
        )

    def test_locked_facts_contain_status(self):
        """With no completions, locked facts must show 'not yet completed'."""
        injection = self._build_cos_injection()
        self.assertIn('Bible reading is not yet completed.', injection)
        self.assertIn('Prayer is not yet completed.', injection)
        self.assertIn('Workout is not yet completed.', injection)
        self.assertIn('No journal entry yet today.', injection)

    def test_locked_facts_rules_present(self):
        """Locked facts must contain enforcement rules."""
        injection = self._build_cos_injection()
        self.assertIn(
            'MUST NOT change their wording, meaning, or completion status',
            injection,
        )

    def test_patterns_labeled_advisory(self):
        """Pattern/signal sections must be labeled as advisory."""
        injection = self._build_cos_injection()
        self.assertIn(
            'PATTERNS & SIGNALS (advisory',
            injection,
        )

    def test_locked_facts_anchor_at_end(self):
        """Locked facts must be repeated at the end (protected from truncation)."""
        injection = self._build_cos_injection()
        # The locked facts block should appear twice (top and bottom)
        first = injection.find('LOCKED FACT STATEMENTS')
        second = injection.find('LOCKED FACT STATEMENTS', first + 100)
        self.assertGreater(
            second, -1,
            "Locked facts not repeated at end of prompt",
        )
        total_len = len(injection)
        self.assertGreater(
            second / total_len, 0.8,
            f"End locked facts at {second/total_len:.0%} — should be near end",
        )

    def test_locked_facts_before_patterns(self):
        """LOCKED FACTS must appear before PATTERNS in the prompt."""
        injection = self._build_cos_injection()
        facts_pos = injection.find('LOCKED FACT STATEMENTS')
        patterns_pos = injection.find('PATTERNS & SIGNALS')
        self.assertGreater(facts_pos, -1)
        self.assertGreater(patterns_pos, -1)
        self.assertLess(
            facts_pos, patterns_pos,
            "LOCKED FACTS must come before PATTERNS in prompt",
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

    def _build_locked_facts_nothing_done(self):
        """Build locked facts: nothing completed today."""
        from apps.ai.cos_fact_statements import (
            _build_faith_summary,
            _build_routine_summary,
            _build_task_summary,
            _build_workout_summary,
            _build_journal_summary,
            _build_overall_summary,
        )
        raw = {
            'prayer_done': False,
            'bible_done': False,
            'workout_done': False,
            'journal_done': False,
            'routine_done': 0,
            'routine_total': 5,
            'tasks_done': 0,
        }
        return {
            'faith_summary': _build_faith_summary(False, False),
            'routine_summary': _build_routine_summary(0, 5, []),
            'task_summary': _build_task_summary(0),
            'workout_summary': _build_workout_summary(False),
            'journal_summary': _build_journal_summary(False),
            'overall_summary': _build_overall_summary(raw),
            '_raw': raw,
        }

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

    def test_case_1_fabricated_completion_rejected(self):
        """TEST CASE 1: Response claiming prayer is done must be rejected."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        bad_response = (
            "Great start to your morning! Your prayer and Bible reading "
            "have been completed. Now let's focus on your workout."
        )
        result, violations = validate_locked_facts(
            bad_response, locked, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED a fabricated response: {bad_response}"
        )
        domains = [v['domain'] for v in violations]
        self.assertIn('prayer', domains)
        self.assertIn('bible_reading', domains)

    def test_case_2_false_praise_rejected(self):
        """TEST CASE 2: 'Great start' with nothing done must be rejected."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        bad_response = (
            "You're off to a great start this morning! Keep the momentum "
            "going."
        )
        result, violations = validate_locked_facts(
            bad_response, locked, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED false praise: {bad_response}"
        )

    def test_case_3_honest_response_passes(self):
        """TEST CASE 3: Honest 'nothing done' response must PASS."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        good_response = (
            "Nothing from your morning routine has been completed yet. "
            "Let's start with one item — prayer would be a good first step."
        )
        result, violations = validate_locked_facts(
            good_response, locked, self.user, allow_regenerate=True,
        )
        self.assertEqual(
            len(violations), 0,
            f"Validator REJECTED an honest response: {violations}"
        )

    def test_case_4_direct_no_answer_passes(self):
        """TEST CASE 4: Direct 'No' to completion question must PASS."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        good_response = (
            "No, neither prayer nor Bible reading are completed today. "
            "Would you like to start with prayer?"
        )
        result, violations = validate_locked_facts(
            good_response, locked, self.user, allow_regenerate=True,
        )
        self.assertEqual(
            len(violations), 0,
            f"Validator REJECTED an honest 'No' answer: {violations}"
        )

    def test_case_5_positive_reframe_without_lying_passes(self):
        """TEST CASE 5: Positive reframe without fabrication must PASS."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        good_response = (
            "Your morning routine hasn't started yet, but you've got the "
            "whole day ahead of you. The fact that you're checking in shows "
            "you're ready to move. Start with prayer — that sets the tone "
            "for everything else."
        )
        result, violations = validate_locked_facts(
            good_response, locked, self.user, allow_regenerate=True,
        )
        self.assertEqual(
            len(violations), 0,
            f"Validator REJECTED a positive-but-honest reframe: {violations}"
        )

    def test_case_6_strong_morning_rejected(self):
        """TEST CASE 6: 'Strong morning' with nothing done must be rejected."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        bad_response = (
            "Strong morning so far! You've been consistent this week."
        )
        result, violations = validate_locked_facts(
            bad_response, locked, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED 'strong morning' with nothing done"
        )

    def test_case_7_workout_done_claim_rejected(self):
        """TEST CASE 7: Claiming workout is done when not must be rejected."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()

        bad_response = (
            "Your workout is done for the day. Nice work getting that in "
            "early."
        )
        result, violations = validate_locked_facts(
            bad_response, locked, self.user, allow_regenerate=True,
        )
        self.assertTrue(
            len(violations) > 0,
            f"Validator PASSED fabricated workout completion"
        )
        domains = [v['domain'] for v in violations]
        self.assertIn('workout', domains)

    def test_case_8_completed_domain_passes(self):
        """TEST CASE 8: Claiming done for actually-done domain must PASS."""
        from apps.ai.cos_truth_validator import validate_locked_facts
        locked = self._build_locked_facts_nothing_done()
        # Override: prayer IS done
        locked['_raw']['prayer_done'] = True
        locked['faith_summary'] = (
            "Bible reading is not yet completed. Prayer is complete."
        )

        good_response = (
            "Prayer is done for the day. Bible reading is still pending — "
            "want to start that next?"
        )
        result, violations = validate_locked_facts(
            good_response, locked, self.user, allow_regenerate=True,
        )
        prayer_violations = [
            v for v in violations if v['domain'] == 'prayer'
        ]
        self.assertEqual(
            len(prayer_violations), 0,
            "Validator wrongly flagged a truthful prayer completion claim"
        )
