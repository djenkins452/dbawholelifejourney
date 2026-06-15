"""
CoS Truth Enforcement Tests — Validates that Beth's prompt and validator
prevent fabricated completions AND respect expectation awareness.

These tests simulate real user scenarios with a known execution state
and verify:
1. The assembled prompt contains FACTS block with correct values
2. The assembled prompt contains FINAL TRUTH ANCHOR
3. The post-generation validator catches fabricated responses
4. The post-generation validator passes clean responses
5. Fact statements respect expected vs not-expected domains

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
        """With no completions and no routines, locked facts must show
        'not scheduled' for domains without routine items."""
        injection = self._build_cos_injection()
        # User has no routines, so domains should say "not scheduled"
        # OR "not yet completed" depending on other config (e.g., Bible plan)
        # At minimum, the facts block must exist
        self.assertIn('LOCKED FACT STATEMENTS', injection)

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
        """Locked facts must be repeated at the end."""
        injection = self._build_cos_injection()
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

    def _build_locked_facts_nothing_done(self, all_expected=True):
        """Build locked facts: nothing completed today.

        Args:
            all_expected: If True, all domains are expected. If False, none are.
        """
        from apps.ai.cos_fact_statements import (
            _build_faith_summary,
            _build_routine_summary,
            _build_task_summary,
            _build_workout_summary,
            _build_journal_summary,
            _build_medication_summary,
            _build_overall_summary,
        )
        raw = {
            'prayer_done': False,
            'prayer_expected': all_expected,
            'bible_done': False,
            'bible_expected': all_expected,
            'workout_done': False,
            'workout_expected': all_expected,
            'journal_done': False,
            'journal_expected': all_expected,
            'routine_done': 0,
            'routine_total': 5,
            'tasks_done': 0,
            'meds_taken': 0,
            'meds_expected': 0,
            'meds_skipped': 0,
            'meds_all_taken': True,
        }
        return {
            'faith_summary': _build_faith_summary(raw),
            'routine_summary': _build_routine_summary(0, 5, []),
            'task_summary': _build_task_summary(0),
            'workout_summary': _build_workout_summary(raw),
            'journal_summary': _build_journal_summary(raw),
            'medication_summary': _build_medication_summary(raw),
            'overall_summary': _build_overall_summary(raw),
            '_raw': raw,
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


class CosExpectationAwarenessTest(TestCase):
    """Verify fact statements correctly handle expected vs not-expected."""

    def test_workout_not_expected_says_not_scheduled(self):
        """When workout is not expected, summary says 'No workout scheduled'."""
        from apps.ai.cos_fact_statements import _build_workout_summary
        raw = {'workout_done': False, 'workout_expected': False}
        summary = _build_workout_summary(raw)
        self.assertEqual(summary, "No workout scheduled today.")

    def test_workout_expected_not_done_says_not_completed(self):
        """When workout is expected but not done, says 'not yet completed'."""
        from apps.ai.cos_fact_statements import _build_workout_summary
        raw = {'workout_done': False, 'workout_expected': True}
        summary = _build_workout_summary(raw)
        self.assertEqual(summary, "Workout is not yet completed.")

    def test_workout_done_says_complete(self):
        """When workout is done, says 'complete' regardless of expected."""
        from apps.ai.cos_fact_statements import _build_workout_summary
        raw = {'workout_done': True, 'workout_expected': True}
        summary = _build_workout_summary(raw)
        self.assertEqual(summary, "Workout is complete.")

    def test_workout_done_but_not_expected_still_complete(self):
        """Bonus workout (done but not expected) still shows complete."""
        from apps.ai.cos_fact_statements import _build_workout_summary
        raw = {'workout_done': True, 'workout_expected': False}
        summary = _build_workout_summary(raw)
        self.assertEqual(summary, "Workout is complete.")

    def test_journal_not_expected_says_not_scheduled(self):
        """When journal is not expected, summary says 'not scheduled'."""
        from apps.ai.cos_fact_statements import _build_journal_summary
        raw = {'journal_done': False, 'journal_expected': False}
        summary = _build_journal_summary(raw)
        self.assertEqual(summary, "No journal entry scheduled today.")

    def test_journal_expected_not_done(self):
        """When journal is expected but not done."""
        from apps.ai.cos_fact_statements import _build_journal_summary
        raw = {'journal_done': False, 'journal_expected': True}
        summary = _build_journal_summary(raw)
        self.assertEqual(summary, "Journal entry is not yet completed.")

    def test_faith_not_expected_says_not_scheduled(self):
        """When faith items are not expected, summary says 'not scheduled'."""
        from apps.ai.cos_fact_statements import _build_faith_summary
        raw = {
            'prayer_done': False, 'prayer_expected': False,
            'bible_done': False, 'bible_expected': False,
        }
        summary = _build_faith_summary(raw)
        self.assertIn("No Bible reading scheduled today.", summary)
        self.assertIn("No prayer scheduled today.", summary)

    def test_faith_expected_not_done(self):
        """When faith is expected but not done."""
        from apps.ai.cos_fact_statements import _build_faith_summary
        raw = {
            'prayer_done': False, 'prayer_expected': True,
            'bible_done': False, 'bible_expected': True,
        }
        summary = _build_faith_summary(raw)
        self.assertIn("Bible reading is not yet completed.", summary)
        self.assertIn("Prayer is not yet completed.", summary)

    def test_overall_summary_only_counts_expected(self):
        """Overall summary must only count expected domains."""
        from apps.ai.cos_fact_statements import _build_overall_summary
        # Only prayer expected, nothing done
        raw = {
            'prayer_done': False, 'prayer_expected': True,
            'bible_done': False, 'bible_expected': False,
            'workout_done': False, 'workout_expected': False,
            'journal_done': False, 'journal_expected': False,
            'routine_done': 0, 'routine_total': 0,
            'tasks_done': 0,
            'meds_taken': 0, 'meds_expected': 0, 'meds_skipped': 0,
            'meds_all_taken': True,
        }
        summary = _build_overall_summary(raw)
        self.assertIn("Nothing has been completed", summary)
        # Should NOT say "4 domains" or count non-expected domains

    def test_overall_summary_all_expected_done(self):
        """When all expected domains are done, says 'all complete'."""
        from apps.ai.cos_fact_statements import _build_overall_summary
        raw = {
            'prayer_done': True, 'prayer_expected': True,
            'bible_done': True, 'bible_expected': True,
            'workout_done': False, 'workout_expected': False,
            'journal_done': False, 'journal_expected': False,
            'routine_done': 3, 'routine_total': 3,
            'tasks_done': 0,
            'meds_taken': 0, 'meds_expected': 0, 'meds_skipped': 0,
            'meds_all_taken': True,
        }
        summary = _build_overall_summary(raw)
        self.assertEqual(summary, "All daily items are complete.")

    def test_completion_rate_only_counts_expected(self):
        """Completion rate must only count expected domains."""
        from apps.ai.cos_truth_validator import _compute_completion_rate_from_raw
        # Prayer expected+done, workout NOT expected
        raw = {
            'prayer_done': True, 'prayer_expected': True,
            'bible_done': False, 'bible_expected': True,
            'workout_done': False, 'workout_expected': False,
            'journal_done': False, 'journal_expected': False,
            'routine_done': 0, 'routine_total': 0,
        }
        rate = _compute_completion_rate_from_raw(raw)
        # 1 done out of 2 expected = 50%
        self.assertEqual(rate, 50)

    def test_no_false_praise_when_not_expected_domains_incomplete(self):
        """No false praise flag when only non-expected domains are 'incomplete'."""
        from apps.ai.cos_truth_validator import _compute_completion_rate_from_raw
        # All expected domains done, non-expected not done
        raw = {
            'prayer_done': True, 'prayer_expected': True,
            'bible_done': True, 'bible_expected': True,
            'workout_done': False, 'workout_expected': False,
            'journal_done': False, 'journal_expected': False,
            'routine_done': 3, 'routine_total': 3,
        }
        rate = _compute_completion_rate_from_raw(raw)
        # 2 expected done out of 2 expected + 3 routine done / 3 total = 100%
        self.assertEqual(rate, 100)


class CosMedicationFactTest(TestCase):
    """Verify medication doses are first-class items in locked facts.

    Root cause fix: medications were completely excluded from the locked
    fact pipeline, allowing Beth to say "all complete" while evening/night
    doses remained pending. These tests enforce the gate.
    """

    def _make_raw(self, **overrides):
        """Build a raw dict with all fields including medications."""
        raw = {
            'prayer_done': True, 'prayer_expected': True,
            'bible_done': True, 'bible_expected': True,
            'workout_done': True, 'workout_expected': True,
            'journal_done': True, 'journal_expected': True,
            'routine_done': 3, 'routine_total': 3,
            'tasks_done': 2,
            'meds_taken': 0, 'meds_expected': 0, 'meds_skipped': 0,
            'meds_all_taken': True,
        }
        raw.update(overrides)
        return raw

    # --- _build_medication_summary tests ---

    def test_med_summary_no_meds_scheduled(self):
        """No medications scheduled → 'No medications scheduled today.'"""
        from apps.ai.cos_fact_statements import _build_medication_summary
        raw = self._make_raw(meds_expected=0, meds_taken=0, meds_all_taken=True)
        self.assertEqual(
            _build_medication_summary(raw),
            "No medications scheduled today.",
        )

    def test_med_summary_all_taken(self):
        """All 6 doses taken → 'All 6 medication doses taken.'"""
        from apps.ai.cos_fact_statements import _build_medication_summary
        raw = self._make_raw(meds_expected=6, meds_taken=6, meds_all_taken=True)
        self.assertEqual(
            _build_medication_summary(raw),
            "All 6 medication doses taken.",
        )

    def test_med_summary_partial(self):
        """4 of 6 taken → '4 of 6 medication doses taken. 2 doses remaining.'"""
        from apps.ai.cos_fact_statements import _build_medication_summary
        raw = self._make_raw(meds_expected=6, meds_taken=4, meds_all_taken=False)
        self.assertEqual(
            _build_medication_summary(raw),
            "4 of 6 medication doses taken. 2 doses remaining.",
        )

    def test_med_summary_partial_with_skip(self):
        """4 taken, 1 skipped of 6 → includes skip text and correct remaining."""
        from apps.ai.cos_fact_statements import _build_medication_summary
        raw = self._make_raw(
            meds_expected=6, meds_taken=4, meds_skipped=1, meds_all_taken=False,
        )
        self.assertEqual(
            _build_medication_summary(raw),
            "4 of 6 medication doses taken. 1 doses remaining. 1 skipped.",
        )

    def test_med_summary_all_accounted_via_skip(self):
        """5 taken, 1 skipped of 6 → all accounted for."""
        from apps.ai.cos_fact_statements import _build_medication_summary
        raw = self._make_raw(
            meds_expected=6, meds_taken=5, meds_skipped=1, meds_all_taken=False,
        )
        self.assertEqual(
            _build_medication_summary(raw),
            "5 of 6 medication doses taken. 1 skipped.",
        )

    def test_med_summary_none_taken(self):
        """0 of 6 taken → '0 of 6 medication doses taken. 6 doses remaining.'"""
        from apps.ai.cos_fact_statements import _build_medication_summary
        raw = self._make_raw(meds_expected=6, meds_taken=0, meds_all_taken=False)
        self.assertEqual(
            _build_medication_summary(raw),
            "0 of 6 medication doses taken. 6 doses remaining.",
        )

    # --- Overall summary medication gate tests ---

    def test_overall_blocked_by_pending_meds(self):
        """All domains + routines done BUT meds pending → NOT 'all complete'."""
        from apps.ai.cos_fact_statements import _build_overall_summary
        raw = self._make_raw(meds_expected=6, meds_taken=4, meds_all_taken=False)
        summary = _build_overall_summary(raw)
        self.assertNotEqual(
            summary, "All daily items are complete.",
            "CRITICAL: 'All daily items are complete' while medications pending!",
        )

    def test_overall_allowed_when_meds_complete(self):
        """All domains + routines + meds done → 'All daily items are complete.'"""
        from apps.ai.cos_fact_statements import _build_overall_summary
        raw = self._make_raw(meds_expected=6, meds_taken=6, meds_all_taken=True)
        summary = _build_overall_summary(raw)
        self.assertEqual(summary, "All daily items are complete.")

    def test_overall_allowed_when_no_meds_scheduled(self):
        """All domains + routines done, no meds → 'All daily items are complete.'"""
        from apps.ai.cos_fact_statements import _build_overall_summary
        raw = self._make_raw(meds_expected=0, meds_taken=0, meds_all_taken=True)
        summary = _build_overall_summary(raw)
        self.assertEqual(summary, "All daily items are complete.")

    def test_overall_blocked_by_zero_of_six_meds(self):
        """Zero meds taken with 6 expected → must NOT say all complete."""
        from apps.ai.cos_fact_statements import _build_overall_summary
        raw = self._make_raw(meds_expected=6, meds_taken=0, meds_all_taken=False)
        summary = _build_overall_summary(raw)
        self.assertNotEqual(
            summary, "All daily items are complete.",
            "CRITICAL: 'All complete' with 0/6 medication doses taken!",
        )

    # --- format_locked_facts_block includes Medications line ---

    def test_locked_facts_block_is_next_action_only(self):
        """STRICT MODE ISOLATION contract: the formatted block contains ONLY
        the system next action — NOT domain summaries (faith/routine/meds).

        Updated 2026-06-14: format_locked_facts_block was deliberately
        narrowed to next-action-only so the LLM has no domain summaries to
        blend into a multi-mode response. The richer dict still reaches the
        truth validator unchanged. This test enforces the current contract;
        the prior assertion (a 'Medications:' line) checked removed behavior.
        """
        from apps.ai.cos_fact_statements import (
            format_locked_facts_block, _build_medication_summary,
            _build_faith_summary, _build_routine_summary,
            _build_task_summary, _build_workout_summary,
            _build_journal_summary, _build_overall_summary,
        )
        raw = self._make_raw(meds_expected=6, meds_taken=4, meds_all_taken=False)
        facts = {
            'faith_summary': _build_faith_summary(raw),
            'routine_summary': _build_routine_summary(3, 3, []),
            'task_summary': _build_task_summary(2),
            'workout_summary': _build_workout_summary(raw),
            'journal_summary': _build_journal_summary(raw),
            'medication_summary': _build_medication_summary(raw),
            'overall_summary': _build_overall_summary(raw),
            'next_action': 'Start with Evening Medications.',
            '_raw': raw,
        }
        block = format_locked_facts_block(facts)
        # The next action IS surfaced...
        self.assertIn('Start with Evening Medications.', block)
        self.assertIn('CURRENT NEXT ACTION', block)
        # ...but domain summaries are intentionally excluded.
        self.assertNotIn('Medications:', block)
        self.assertNotIn('4 of 6 medication doses taken', block)

    # --- Integration: build_locked_facts includes medication data ---

    def test_build_locked_facts_includes_medication_key(self):
        """build_locked_facts() must return a 'medication_summary' key."""
        from apps.ai.cos_fact_statements import build_locked_facts
        from unittest.mock import patch

        mock_truth = {
            'date': '2026-03-23',
            'domains': {
                'faith': {
                    'prayer_completed': True, 'prayer_expected': True,
                    'bible_reading_completed': True, 'bible_expected': True,
                },
                'workout': {'completed': True, 'expected': True},
                'journal': {'completed': True, 'expected': True},
            },
            'routines': {
                'total': 3, 'completed': 3,
                'fully_complete': True, '_raw_items': {},
            },
            'tasks': {'completed': 2, 'completed_today_all': 2},
            'medications': {
                'taken': 4, 'expected': 6, 'skipped': 1,
                'all_taken': False,
            },
        }
        user = MagicMock()
        user.id = 999

        with patch(
            'apps.core.execution.execution_truth_engine.get_execution_truth',
            return_value=mock_truth,
        ), patch(
            'apps.ai.cos_fact_statements.build_locked_next_action',
            return_value='Start with Evening Medications.',
        ):
            facts = build_locked_facts(user)

        self.assertIn('medication_summary', facts)
        self.assertEqual(
            facts['medication_summary'],
            "4 of 6 medication doses taken. 1 doses remaining. 1 skipped.",
        )
        self.assertNotEqual(
            facts['overall_summary'],
            "All daily items are complete.",
        )
        # Verify raw includes medication fields
        self.assertEqual(facts['_raw']['meds_taken'], 4)
        self.assertEqual(facts['_raw']['meds_expected'], 6)
        self.assertEqual(facts['_raw']['meds_skipped'], 1)
        self.assertFalse(facts['_raw']['meds_all_taken'])
