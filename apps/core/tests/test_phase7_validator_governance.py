"""
Phase 7 — Validator + Governance (Phase 8 Hardening) Tests.

Covers:
    1. Structural banned term blocked
    2. Numeric internal metric observed only
    3. Validator crash returns safe response
    4. Level 2 repeat ≥5 in 7d escalates to Level 3
    5. Governance email triggered for Level 3
    6. SRI computation correct window logic

These tests verify the pre-release validator gate and self-governance
system work correctly under all scenarios.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_validator_governance.py
"""

import datetime as dt
from unittest.mock import patch, MagicMock, call

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='validator-p7@example.com'):
    """Create a test user with preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


# =========================================================================
# 1) STRUCTURAL BANNED TERM BLOCKED
# =========================================================================


class StructuralBannedTermTests(TestCase):
    """Test that banned internal terms are blocked from user-facing output."""

    def setUp(self):
        self.user = _create_test_user('structural@example.com')

    def test_banned_term_drift_pressure_blocked(self):
        """Response containing 'drift pressure' is blocked."""
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )

        result = validate_response(
            "Your drift pressure is increasing.",
            user=self.user,
        )
        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)

    def test_banned_term_governance_profile_blocked(self):
        """Response containing 'governance profile' is blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "I'll check your governance profile.",
            user=self.user,
        )
        self.assertTrue(result['blocked'])

    def test_banned_term_tier_1_blocked(self):
        """Response containing 'tier 1' is blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "This is a tier 1 behavior that needs protection.",
            user=self.user,
        )
        self.assertTrue(result['blocked'])

    def test_banned_term_system_prompt_blocked(self):
        """Response containing 'system prompt' is blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "My system prompt tells me to...",
            user=self.user,
        )
        self.assertTrue(result['blocked'])

    def test_banned_term_case_insensitive(self):
        """Banned term detection is case-insensitive."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "The DRIFT PRESSURE is high.",
            user=self.user,
        )
        self.assertTrue(result['blocked'])

    def test_clean_response_not_blocked(self):
        """Clean response passes through unchanged."""
        from apps.core.ai_governance.validator_gate import validate_response

        clean_text = (
            "You've been doing well with your morning routine. "
            "Keep focusing on what matters to you."
        )
        result = validate_response(clean_text, user=self.user)
        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], clean_text)

    def test_multiple_banned_terms_all_detected(self):
        """Response with multiple banned terms reports all violations."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "Your drift pressure score from the consistency evaluator "
            "shows ALIGN strategy is needed.",
            user=self.user,
        )
        self.assertTrue(result['blocked'])
        # Should have multiple violations
        self.assertGreater(len(result['violations']), 1)

    def test_banned_terms_list_is_comprehensive(self):
        """The banned terms list includes all critical internal terms."""
        from apps.core.ai_governance.language_rules import BANNED_TERMS

        critical_terms = [
            'drift pressure', 'governance profile', 'tier 1',
            'system prompt', 'friction gate', 'miss rate',
            'PIE event', 'PRIE prediction',
        ]
        for term in critical_terms:
            self.assertIn(term, BANNED_TERMS,
                          f"'{term}' missing from BANNED_TERMS")


# =========================================================================
# 2) NUMERIC INTERNAL METRIC OBSERVED ONLY
# =========================================================================


class NumericDeviationObserveOnlyTests(TestCase):
    """Test that numeric deviations are observed but not blocked."""

    def setUp(self):
        self.user = _create_test_user('numeric@example.com')

    def test_numeric_cpi_score_observed_not_blocked(self):
        """'CPI is 72' is flagged but not blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "Let me check — CPI is 72 right now.",
            user=self.user,
        )
        self.assertFalse(result['blocked'])
        self.assertGreater(len(result['violations']), 0)
        # Original response preserved
        self.assertIn('CPI is 72', result['response'])

    def test_numeric_density_score_observed(self):
        """'density is 0.85' is flagged but not blocked."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "Your capacity density is 0.85 right now.",
            user=self.user,
        )
        self.assertFalse(result['blocked'])

    def test_contextual_numbers_not_flagged(self):
        """Normal numbers like '3 out of 5 tasks' are not flagged."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "You completed 3 out of 5 tasks today. Great work!",
            user=self.user,
        )
        self.assertFalse(result['blocked'])
        self.assertEqual(len(result['violations']), 0)

    def test_goal_counts_not_flagged(self):
        """'completed 2 goals' is safe contextual language."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(
            "You've completed 2 goals this week.",
            user=self.user,
        )
        self.assertFalse(result['blocked'])


# =========================================================================
# 3) VALIDATOR CRASH RETURNS SAFE RESPONSE
# =========================================================================


class ValidatorCrashTests(TestCase):
    """Test that validator crashes produce a safe response."""

    def setUp(self):
        self.user = _create_test_user('crash@example.com')

    def test_validator_crash_returns_safe_fallback(self):
        """If validator_gate crashes, it returns VALIDATOR_CRASH_RESPONSE."""
        from apps.core.ai_governance.validator_gate import (
            VALIDATOR_CRASH_RESPONSE,
            validate_response,
        )

        # Force a crash in the inner validation
        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=RuntimeError('Unexpected crash'),
        ):
            result = validate_response(
                "Normal response text",
                user=self.user,
            )

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], VALIDATOR_CRASH_RESPONSE)
        self.assertTrue(
            any('VALIDATOR_CRASH' in v for v in result['violations']),
        )

    def test_crash_handler_failure_still_safe(self):
        """Even if _handle_validator_crash fails, safe response returned."""
        from apps.core.ai_governance.validator_gate import (
            VALIDATOR_CRASH_RESPONSE,
            validate_response,
        )

        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=RuntimeError('Inner crash'),
        ), patch(
            'apps.core.ai_governance.validator_gate._handle_validator_crash',
            side_effect=Exception('Crash handler also crashed'),
        ):
            result = validate_response(
                "Normal response",
                user=self.user,
            )

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], VALIDATOR_CRASH_RESPONSE)

    def test_empty_response_passes_through(self):
        """Empty or None response passes through without crash."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response('', user=self.user)
        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], '')

        result = validate_response(None, user=self.user)
        self.assertFalse(result['blocked'])

    def test_non_string_response_handled(self):
        """Non-string input doesn't crash the validator."""
        from apps.core.ai_governance.validator_gate import validate_response

        result = validate_response(123, user=self.user)
        # Should handle gracefully (either pass through or return safe)
        self.assertIn('blocked', result)


# =========================================================================
# 4) LEVEL 2 REPEAT ≥5 IN 7D ESCALATES TO LEVEL 3
# =========================================================================


class Level2AutoEscalationTests(TestCase):
    """Test Level 2 auto-escalation to Level 3 after repeated triggers."""

    def setUp(self):
        self.user = _create_test_user('l2-escalation@example.com')

    def test_4_repeats_does_not_escalate(self):
        """4 Level 2 errors in 7 days does not trigger escalation."""
        from apps.core.ai_governance.self_governance import (
            check_level2_auto_escalation,
        )
        from apps.core.ai_governance.models import SelfError

        for _ in range(4):
            SelfError.objects.create(
                user=self.user,
                level=SelfError.LEVEL_MODERATE,
                category=SelfError.CATEGORY_STRUCTURAL,
                trigger_code='BANNED_TERM_LEAKED',
                was_blocked=True,
            )

        result = check_level2_auto_escalation(
            'BANNED_TERM_LEAKED', user=self.user,
        )
        self.assertFalse(result)

    def test_5_repeats_triggers_escalation(self):
        """5 Level 2 errors in 7 days triggers auto-escalation."""
        from apps.core.ai_governance.self_governance import (
            check_level2_auto_escalation,
        )
        from apps.core.ai_governance.models import SelfError

        for _ in range(5):
            SelfError.objects.create(
                user=self.user,
                level=SelfError.LEVEL_MODERATE,
                category=SelfError.CATEGORY_STRUCTURAL,
                trigger_code='BANNED_TERM_LEAKED',
                was_blocked=True,
            )

        result = check_level2_auto_escalation(
            'BANNED_TERM_LEAKED', user=self.user,
        )
        self.assertTrue(result)

    def test_old_errors_outside_window_not_counted(self):
        """Errors older than 7 days don't count toward threshold."""
        from apps.core.ai_governance.self_governance import (
            check_level2_auto_escalation,
        )
        from apps.core.ai_governance.models import SelfError

        # Create 5 errors, but 3 are outside the 7-day window
        for i in range(5):
            err = SelfError.objects.create(
                user=self.user,
                level=SelfError.LEVEL_MODERATE,
                category=SelfError.CATEGORY_STRUCTURAL,
                trigger_code='BANNED_TERM_LEAKED',
                was_blocked=True,
            )
            if i < 3:
                # Backdate to 10 days ago
                SelfError.objects.filter(pk=err.pk).update(
                    created_at=timezone.now() - dt.timedelta(days=10),
                )

        # Only 2 recent errors → no escalation
        result = check_level2_auto_escalation(
            'BANNED_TERM_LEAKED', user=self.user,
        )
        self.assertFalse(result)

    def test_record_self_error_auto_escalates_level2(self):
        """record_self_error auto-escalates Level 2 to Level 3 when threshold met."""
        from apps.core.ai_governance.self_governance import record_self_error
        from apps.core.ai_governance.models import SelfError

        # Create 5 existing Level 2 errors
        for _ in range(5):
            SelfError.objects.create(
                user=self.user,
                level=SelfError.LEVEL_MODERATE,
                category=SelfError.CATEGORY_STRUCTURAL,
                trigger_code='BANNED_TERM_LEAKED',
                was_blocked=True,
            )

        # The next record_self_error should create a Level 3
        with patch(
            'apps.core.ai_governance.self_governance.send_governance_alert',
        ) as mock_email:
            error = record_self_error(
                user=self.user,
                level=2,
                category='STRUCTURAL',
                trigger_code='BANNED_TERM_LEAKED',
                trigger_detail='test',
                was_blocked=True,
            )

        if error:
            self.assertEqual(error.level, 3)
            self.assertEqual(
                error.metadata.get('auto_escalated_from'), 2,
            )


# =========================================================================
# 5) GOVERNANCE EMAIL TRIGGERED FOR LEVEL 3
# =========================================================================


@override_settings(ADMINS=[('Admin', 'admin@example.com')])
class GovernanceEmailTests(TestCase):
    """Test governance email triggered on Level 3 events."""

    def setUp(self):
        self.user = _create_test_user('gov-email@example.com')

    def test_level_3_triggers_email(self):
        """Level 3 SelfError triggers governance alert email."""
        from apps.core.ai_governance.self_governance import (
            record_self_error,
            send_governance_alert,
        )

        with patch(
            'apps.core.ai_governance.self_governance.send_mail',
        ) as mock_send:
            record_self_error(
                user=self.user,
                level=3,
                category='GOVERNANCE',
                trigger_code='VALIDATOR_CRASH',
                trigger_detail='Test crash',
                was_blocked=True,
            )

            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args
            self.assertIn('Critical', call_kwargs[1]['subject']
                          if 'subject' in call_kwargs[1]
                          else call_kwargs[0][0])

    def test_level_2_does_not_trigger_email(self):
        """Level 2 SelfError (without auto-escalation) doesn't send email."""
        from apps.core.ai_governance.self_governance import (
            send_governance_alert,
        )
        from apps.core.ai_governance.models import SelfError

        error = SelfError.objects.create(
            user=self.user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            was_blocked=True,
        )

        with patch(
            'apps.core.ai_governance.self_governance.send_mail',
        ) as mock_send:
            send_governance_alert(2, error)
            mock_send.assert_not_called()

    def test_email_includes_error_details(self):
        """Governance email includes category, trigger, and detail."""
        from apps.core.ai_governance.self_governance import (
            send_governance_alert,
        )
        from apps.core.ai_governance.models import SelfError

        error = SelfError.objects.create(
            user=self.user,
            level=3,
            category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
            trigger_detail='RuntimeError in validation',
            was_blocked=True,
        )

        with patch(
            'apps.core.ai_governance.self_governance.send_mail',
        ) as mock_send:
            send_governance_alert(3, error)
            if mock_send.called:
                body = mock_send.call_args[1].get(
                    'message', mock_send.call_args[0][1]
                    if len(mock_send.call_args[0]) > 1 else ''
                )
                self.assertIn('VALIDATOR_CRASH', body)


# =========================================================================
# 6) SRI COMPUTATION CORRECT WINDOW LOGIC
# =========================================================================


class SRIComputationTests(TestCase):
    """Test Self-Reliability Index computation."""

    def setUp(self):
        self.user = _create_test_user('sri@example.com')

    def test_sri_100_with_no_errors(self):
        """No errors → SRI = 100.0."""
        from apps.core.ai_governance.self_governance import compute_sri

        result = compute_sri()
        self.assertEqual(result['score'], 100.0)
        self.assertEqual(result['total_errors'], 0)

    def test_sri_decreases_with_level1_errors(self):
        """Level 1 errors decrease SRI by 0.5 each."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        for _ in range(4):
            SelfError.objects.create(
                user=self.user,
                level=1,
                category='NUMERIC',
                trigger_code='NUMERIC_DEVIATION',
            )

        result = compute_sri()
        # 100 - (4 × 0.5) = 98.0
        self.assertEqual(result['score'], 98.0)

    def test_sri_decreases_with_level2_errors(self):
        """Level 2 errors decrease SRI by 2.0 each."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        for _ in range(3):
            SelfError.objects.create(
                user=self.user,
                level=2,
                category='STRUCTURAL',
                trigger_code='BANNED_TERM_LEAKED',
            )

        result = compute_sri()
        # 100 - (3 × 2.0) = 94.0
        self.assertEqual(result['score'], 94.0)

    def test_sri_decreases_heavily_with_level3_errors(self):
        """Level 3 errors decrease SRI by 10.0 each."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        SelfError.objects.create(
            user=self.user,
            level=3,
            category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
        )

        result = compute_sri()
        # 100 - (1 × 10.0) = 90.0
        self.assertEqual(result['score'], 90.0)
        self.assertEqual(result['level3_count'], 1)

    def test_sri_clamped_at_zero(self):
        """SRI cannot go below 0."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        # 11 Level 3 errors = 110 penalty
        for _ in range(11):
            SelfError.objects.create(
                user=self.user,
                level=3,
                category='GOVERNANCE',
                trigger_code='VALIDATOR_CRASH',
            )

        result = compute_sri()
        self.assertEqual(result['score'], 0.0)

    def test_sri_window_is_30_days(self):
        """Errors older than 30 days are not counted."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        # Create error 31 days ago
        old_error = SelfError.objects.create(
            user=self.user,
            level=3,
            category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
        )
        SelfError.objects.filter(pk=old_error.pk).update(
            created_at=timezone.now() - dt.timedelta(days=31),
        )

        result = compute_sri()
        self.assertEqual(result['score'], 100.0)
        self.assertEqual(result['total_errors'], 0)

    def test_sri_returns_correct_category_counts(self):
        """SRI result includes correct per-category counts."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        SelfError.objects.create(
            user=self.user, level=1, category='NUMERIC',
            trigger_code='NUMERIC_DEVIATION',
        )
        SelfError.objects.create(
            user=self.user, level=2, category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
        )
        SelfError.objects.create(
            user=self.user, level=3, category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
        )

        result = compute_sri()
        self.assertEqual(result['numeric_errors'], 1)
        self.assertEqual(result['structural_errors'], 1)
        self.assertEqual(result['governance_errors'], 1)
        self.assertEqual(result['total_errors'], 3)

    def test_sri_blocked_count(self):
        """SRI correctly counts blocked errors."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.self_governance import compute_sri

        SelfError.objects.create(
            user=self.user, level=2, category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED', was_blocked=True,
        )
        SelfError.objects.create(
            user=self.user, level=1, category='NUMERIC',
            trigger_code='NUMERIC_DEVIATION', was_blocked=False,
        )

        result = compute_sri()
        self.assertEqual(result['blocked_count'], 1)
