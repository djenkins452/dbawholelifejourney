"""
Phase 8 — Validator Gate Tests.

Tests for the pre-release deterministic validator that inspects LLM responses
before persistence.

Covers:
    - Structural detection (banned terms) → BLOCK
    - Numeric detection (internal scores) → OBSERVE-ONLY
    - Validator crash handling → Level 3 + safe response
    - Hybrid rollout policy
    - DecisionRecord tracing
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


def _create_test_user(email='validator-test@example.com'):
    from apps.users.models import User
    return User.objects.create_user(email=email, password='testpass123')


# =========================================================================
# STRUCTURAL DETECTION — BLOCKING
# =========================================================================


class StructuralDetectionTests(TestCase):
    """Structural violations (banned terms) must block and replace."""

    def setUp(self):
        self.user = _create_test_user()

    def test_banned_term_in_response_is_blocked(self):
        """Response containing 'drift pressure' → blocked, replacement returned."""
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )

        response = "Your drift pressure is rising, so let's focus on your priorities."
        result = validate_response(response, self.user)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)
        self.assertTrue(any('STRUCTURAL' in v for v in result['violations']))

    def test_multiple_banned_terms_blocked(self):
        """Response with multiple banned terms → single block, replacement."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )

        response = (
            "Your governance profile shows tier 1 protection is active, "
            "and the consistency evaluator flagged a miss rate issue."
        )
        result = validate_response(response, self.user)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)
        # At least one SelfError created
        self.assertTrue(SelfError.objects.filter(
            user=self.user,
            category='STRUCTURAL',
            was_blocked=True,
        ).exists())

    def test_clean_response_passes_through(self):
        """No banned terms → original response returned, no SelfError."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Let's focus on your workout today and keep the momentum going."
        result = validate_response(response, self.user)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)
        self.assertEqual(result['violations'], [])
        self.assertFalse(SelfError.objects.filter(user=self.user).exists())

    def test_case_insensitive_banned_term_detection(self):
        """'Drift Pressure' (mixed case) is detected."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Your Drift Pressure has been climbing this week."
        result = validate_response(response, self.user)

        self.assertTrue(result['blocked'])
        self.assertTrue(any('drift pressure' in v.lower() for v in result['violations']))


# =========================================================================
# NUMERIC DETECTION — OBSERVE-ONLY
# =========================================================================


class NumericDetectionTests(TestCase):
    """Numeric deviations are observe-only: log SelfError, return original."""

    def setUp(self):
        self.user = _create_test_user('numeric-test@example.com')

    def test_numeric_threshold_in_response_observed(self):
        """'capacity at 85%' → SelfError logged, was_blocked=False, original returned."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Your schedule looks packed — capacity at 85% today."
        result = validate_response(response, self.user)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], response)
        self.assertTrue(any('NUMERIC' in v for v in result['violations']))

        # SelfError created as observe-only
        err = SelfError.objects.filter(
            user=self.user,
            category='NUMERIC',
        ).first()
        self.assertIsNotNone(err)
        self.assertFalse(err.was_blocked)

    def test_percentage_pattern_detected(self):
        """'pressure index is 72' → observed (not a banned term, but internal numeric)."""
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Your pressure index is 72 today, let's adjust."
        result = validate_response(response, self.user)

        self.assertFalse(result['blocked'])
        self.assertTrue(any('NUMERIC' in v for v in result['violations']))

    def test_acceptable_numbers_not_flagged(self):
        """'you completed 3 out of 5 tasks' → no SelfError."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.validator_gate import validate_response

        response = "Great work — you completed 3 out of 5 tasks this morning."
        result = validate_response(response, self.user)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['violations'], [])
        self.assertFalse(SelfError.objects.filter(user=self.user).exists())


# =========================================================================
# VALIDATOR CRASH HANDLING
# =========================================================================


class ValidatorCrashTests(TestCase):
    """Validator crash → Level 3 SelfError, safe response, OpsAnomaly."""

    def setUp(self):
        self.user = _create_test_user('crash-test@example.com')

    def test_validator_crash_returns_safe_response(self):
        """Internal error → Level 3 SelfError, VALIDATOR_CRASH_RESPONSE returned."""
        from apps.core.ai_governance.models import SelfError
        from apps.core.ai_governance.validator_gate import (
            VALIDATOR_CRASH_RESPONSE,
            validate_response,
        )

        # Mock _validate_response_inner to raise
        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=RuntimeError("unexpected null pointer"),
        ):
            result = validate_response("some LLM output", self.user)

        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], VALIDATOR_CRASH_RESPONSE)
        self.assertTrue(any('VALIDATOR_CRASH' in v for v in result['violations']))

        # SelfError Level 3 created
        err = SelfError.objects.filter(
            user=self.user,
            level=SelfError.LEVEL_CRITICAL,
            trigger_code='VALIDATOR_CRASH',
        ).first()
        self.assertIsNotNone(err)
        self.assertTrue(err.was_blocked)

    def test_validator_crash_never_raises(self):
        """validate_response() NEVER raises, even with catastrophic failure."""
        from apps.core.ai_governance.validator_gate import validate_response

        # Mock both inner validator AND crash handler to raise
        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=RuntimeError("boom"),
        ):
            with patch(
                'apps.core.ai_governance.validator_gate._handle_validator_crash',
                side_effect=RuntimeError("double boom"),
            ):
                # Should still return safely
                result = validate_response("some output", self.user)

        # Returns crash response even if crash handler itself fails
        self.assertTrue(result['blocked'])
        self.assertIn('VALIDATOR_CRASH', result['violations'][0])

    def test_validator_crash_logs_ops_anomaly(self):
        """OpsAnomaly created with VALIDATOR_CRASH type on crash."""
        from apps.core.ai_observability.models import OpsAnomaly
        from apps.core.ai_governance.validator_gate import validate_response

        with patch(
            'apps.core.ai_governance.validator_gate._validate_response_inner',
            side_effect=RuntimeError("kaboom"),
        ):
            validate_response("some output", self.user)

        anomaly = OpsAnomaly.objects.filter(
            anomaly_type='VALIDATOR_CRASH',
            engine_name='VGE',
        ).first()
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly.severity, 'P1')


# =========================================================================
# HYBRID ROLLOUT POLICY
# =========================================================================


class HybridRolloutTests(TestCase):
    """Structural = block; Numeric = observe-only."""

    def setUp(self):
        self.user = _create_test_user('hybrid-test@example.com')

    def test_structural_violation_blocks_response(self):
        """Structural → was_blocked=True, replacement returned."""
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )

        result = validate_response(
            "The system injection shows your tier 2 pattern.",
            self.user,
        )
        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)

    def test_numeric_deviation_observes_only(self):
        """Numeric → was_blocked=False, original returned."""
        from apps.core.ai_governance.validator_gate import validate_response

        original = "Your pressure index is 72 today."
        result = validate_response(original, self.user)

        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], original)

    def test_structural_and_numeric_in_same_response(self):
        """Both structural + numeric → structural takes precedence, blocked."""
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )

        response = (
            "Your noise budget is at capacity at 85% and "
            "the friction gate is active."
        )
        result = validate_response(response, self.user)

        # Structural check runs first and blocks
        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)


# =========================================================================
# DECISION RECORD TRACING
# =========================================================================


class DecisionRecordTracingTests(TestCase):
    """Validator logs DecisionRecord for both blocked and observed responses."""

    def setUp(self):
        self.user = _create_test_user('trace-test@example.com')

    def test_blocked_response_creates_decision_record(self):
        """Structural block → DecisionRecord with type='validation'."""
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_governance.validator_gate import validate_response

        validate_response(
            "Your governance profile indicates PROTECT strategy.",
            self.user,
        )

        dr = DecisionRecord.objects.filter(
            decision_type='validation',
            engine_name='VGE',
            decision='BLOCK_STRUCTURAL',
        ).first()
        self.assertIsNotNone(dr)
        self.assertEqual(dr.confidence, 1.0)

    def test_observed_response_creates_decision_record(self):
        """Numeric observe → DecisionRecord with decision='OBSERVE_NUMERIC'."""
        from apps.core.ai_observability.models import DecisionRecord
        from apps.core.ai_governance.validator_gate import validate_response

        validate_response(
            "Your pressure index is 72 today.",
            self.user,
        )

        dr = DecisionRecord.objects.filter(
            decision_type='validation',
            engine_name='VGE',
            decision='OBSERVE_NUMERIC',
        ).first()
        self.assertIsNotNone(dr)
        self.assertEqual(dr.confidence, 0.7)
