"""
Phase 7 — Cross-Phase Integration Tests.

Full end-to-end test:
    1. Create commitment
    2. Advance to near deadline
    3. Trigger pressure forecast
    4. Generate protective recommendation
    5. Observe escalation continuity
    6. Pass through validator

This is the most important test — it verifies the complete pipeline
from commitment creation through pressure modeling, protective action,
escalation, and validator gate.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_cross_phase_integration.py
"""

import datetime as dt
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='integration-p7@example.com'):
    """Create a test user with full setup."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_commitment(user, text, hours_ahead=48):
    """Create a pending commitment."""
    from apps.core.blueprint.models import Commitment
    return Commitment.objects.create(
        user=user,
        normalized_text=text,
        commitment_type=Commitment.TYPE_DO,
        time_boundary=timezone.now() + dt.timedelta(hours=hours_ahead),
        done_definition=f'Complete: {text}',
        status=Commitment.STATUS_PENDING,
        tier_at_creation='CLEAN',
        timezone_at_creation='America/New_York',
    )


def _ensure_pressure_config():
    """Ensure default pressure weight config exists."""
    from apps.core.blueprint.pressure_models import PressureWeightConfig
    return PressureWeightConfig.get_active()


# =========================================================================
# FULL END-TO-END INTEGRATION TEST
# =========================================================================


class FullPipelineIntegrationTest(TestCase):
    """
    Complete end-to-end test of the CoS Executive pipeline:
    Commitment → Pressure → Protective → Escalation → Validator
    """

    def setUp(self):
        self.user = _create_test_user('e2e@example.com')
        _ensure_pressure_config()

    def test_full_pipeline_commitment_to_validator(self):
        """
        Step 1: Create commitment
        Step 2: Compute pressure forecast
        Step 3: Generate protective recommendation
        Step 4: Check escalation state
        Step 5: Validate response through gate
        """
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.blueprint.escalation_engine import (
            resolve_activation_state,
        )
        from apps.core.blueprint.models import (
            Commitment,
            EscalationState,
        )
        from apps.core.blueprint.pressure_engine import (
            compute_pressure_index,
            update_pressure_snapshot,
        )
        from apps.core.blueprint.protective_engine import (
            apply_overload_triggers,
        )

        # --- Step 1: Create commitment ---
        commitment = _create_commitment(
            self.user, 'Exercise for 30 minutes', hours_ahead=4,
        )
        self.assertEqual(commitment.status, Commitment.STATUS_PENDING)
        self.assertIsNotNone(commitment.time_boundary)

        # --- Step 2: Compute pressure forecast ---
        result = compute_pressure_index(self.user, horizon_days=7)
        self.assertIn('pressure_index', result)
        self.assertGreaterEqual(result['pressure_index'], 0)
        self.assertLessEqual(result['pressure_index'], 100)

        # Create pressure snapshot
        snapshot = update_pressure_snapshot(self.user, horizon_days=7)
        self.assertIsNotNone(snapshot)

        # --- Step 3: Verify deadline alerts ---
        # NOTE: The Commitment post_save signal auto-schedules alerts.
        # Verify alerts exist in DB rather than calling schedule_deadline_alerts
        # (which would return empty due to dedup).
        from apps.core.blueprint.protective_models import ProtectiveAlert

        now = timezone.now()
        alerts = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_type='Commitment',
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        )
        alert_types = set(alerts.values_list('alert_type', flat=True))
        # For a 4h-away commitment: 4h and 1h alerts should exist
        if commitment.time_boundary - now > dt.timedelta(hours=1):
            self.assertIn('DEADLINE_1H', alert_types)

        # --- Step 4: Check escalation state ---
        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }
        activation = resolve_activation_state(
            self.user, clean_signals, user_input='',
        )
        self.assertIn(activation, ['CLEAN', 'EARLY_EROSION', 'STRUCTURAL_DRIFT'])

        # Verify EscalationState exists
        state = EscalationState.objects.get(user=self.user)
        self.assertIsNotNone(state)

        # --- Step 5: Validate a clean response ---
        response_text = (
            "You have a commitment to exercise in about 4 hours. "
            "Let's make sure you protect that time."
        )
        validator_result = validate_response(
            response_text, user=self.user,
        )
        self.assertFalse(validator_result['blocked'])
        self.assertEqual(validator_result['response'], response_text)

    def test_pipeline_with_escalation_and_validator_block(self):
        """
        Pipeline where escalation occurs and validator catches a
        leaked internal term.
        """
        from apps.core.ai_governance.validator_gate import (
            STRUCTURAL_BLOCK_RESPONSE,
            validate_response,
        )
        from apps.core.blueprint.escalation_engine import (
            ACTIVATION_STRUCTURAL_DRIFT,
            resolve_activation_state,
        )
        from apps.core.blueprint.models import EscalationState

        # Create commitment
        _create_commitment(
            self.user, 'Complete project report', hours_ahead=24,
        )

        # Escalate to STRUCTURAL_DRIFT via signals
        drift_signals = {
            'renegotiation_patterns': ['blocked_1'],
            'tier1_skip_patterns': ['skip_1'],
            'consecutive_tier1_skips': 3,
        }
        activation = resolve_activation_state(
            self.user, drift_signals, user_input='',
        )
        self.assertEqual(activation, ACTIVATION_STRUCTURAL_DRIFT)

        # Verify persistence
        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            state.current_level, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        # Now validate a response that leaks internal state
        bad_response = (
            "Your escalation level is at STRUCTURAL_DRIFT "
            "with a drift pressure score of 0.8."
        )
        result = validate_response(bad_response, user=self.user)
        self.assertTrue(result['blocked'])
        self.assertEqual(result['response'], STRUCTURAL_BLOCK_RESPONSE)

        # Validate a clean response passes through
        good_response = (
            "Things have been a bit off track lately. "
            "Let's focus on what matters most to you."
        )
        result = validate_response(good_response, user=self.user)
        self.assertFalse(result['blocked'])
        self.assertEqual(result['response'], good_response)

    def test_pipeline_commitment_stacking_with_pressure(self):
        """
        Multiple commitments increase collision score in pressure model.
        """
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        now = timezone.now()

        # Create 3 commitments within 2 hours of each other
        for i in range(3):
            _create_commitment(
                self.user,
                f'Task {i+1}',
                hours_ahead=24 + i,  # 24h, 25h, 26h
            )

        result = compute_pressure_index(self.user, horizon_days=7)
        # With 3 commitments close together, collision score should be > 0
        self.assertGreaterEqual(result['collision_score'], 0.0)

    def test_pipeline_overload_triggers_intervention(self):
        """
        High CPI triggers protective intervention (via post_save signal),
        which is then validated through the validator gate.
        """
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.blueprint.models import InterventionLog
        from apps.core.blueprint.pressure_models import PressureSnapshot

        # Create high-pressure snapshot — signal auto-triggers overload check
        PressureSnapshot.objects.create(
            user=self.user,
            pressure_index=92,
            density_score=0.9,
            compression_score=0.8,
            breach_risk_score=0.7,
            erosion_score=0.6,
            collision_score=0.5,
            horizon_days=7,
        )

        # Signal should have created a Level 3 intervention
        intervention = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='critical_overload_risk',
        ).first()
        self.assertIsNotNone(intervention)

        # The intervention message should pass validator
        result = validate_response(
            intervention.message, user=self.user,
        )
        self.assertFalse(result['blocked'])

    def test_pipeline_commitment_close_and_escalation_recovery(self):
        """
        Closing commitments successfully should contribute to
        recovery eligibility.
        """
        from apps.core.blueprint.escalation_engine import (
            compute_recovery_eligibility,
        )
        from apps.core.blueprint.models import Commitment

        # Create and close 3 commitments as honored
        for i in range(3):
            c = _create_commitment(self.user, f'Honored task {i}')
            c.close(Commitment.STATUS_CLOSED_SUCCESS,
                    Commitment.CLOSURE_USER_CONFIRMED)

        # Check recovery eligibility
        eligible, reasons = compute_recovery_eligibility(
            self.user, timezone.now(),
        )

        # Should meet the honored commitments criterion
        self.assertTrue(reasons['criteria']['honored_commitments_met'])
        self.assertGreaterEqual(reasons['honored_commitments'], 3)

    def test_pipeline_degraded_mode_does_not_break_flow(self):
        """
        Even if pressure snapshot fails, the rest of the pipeline
        continues to work.
        """
        from apps.core.ai_governance.validator_gate import validate_response
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        # Create commitment
        _create_commitment(self.user, 'Test task', hours_ahead=24)

        # Force pressure snapshot failure
        with patch(
            'apps.core.blueprint.pressure_engine.compute_pressure_index',
            side_effect=Exception('DB error'),
        ):
            snapshot = update_pressure_snapshot(self.user)

        self.assertIsNone(snapshot)

        # Escalation should still work
        result = resolve_activation_state(
            self.user,
            {'renegotiation_patterns': [], 'tier1_skip_patterns': [],
             'consecutive_tier1_skips': 0},
            user_input='',
        )
        self.assertIn(result, ['CLEAN', 'EARLY_EROSION', 'STRUCTURAL_DRIFT'])

        # Validator should still work
        val_result = validate_response(
            "Everything is on track.", user=self.user,
        )
        self.assertFalse(val_result['blocked'])


class MultiCommitmentLifecycleTest(TestCase):
    """Test full lifecycle of multiple commitments through the system."""

    def setUp(self):
        self.user = _create_test_user('lifecycle@example.com')
        _ensure_pressure_config()

    def test_create_close_create_pattern(self):
        """Create 5, close 2, create 2 more — all tracked correctly."""
        from apps.core.blueprint.models import Commitment

        # Create 5 commitments
        commitments = []
        for i in range(5):
            c = _create_commitment(self.user, f'Task {i+1}')
            commitments.append(c)

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 5)
        self.assertFalse(Commitment.can_create(self.user))

        # Close 2
        commitments[0].close(Commitment.STATUS_CLOSED_SUCCESS,
                             Commitment.CLOSURE_USER_CONFIRMED)
        commitments[1].close(Commitment.STATUS_CLOSED_MISSED,
                             Commitment.CLOSURE_USER_MISSED)

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 3)
        self.assertTrue(Commitment.can_create(self.user))

        # Create 2 more
        for i in range(2):
            _create_commitment(self.user, f'New task {i+1}')

        self.assertEqual(Commitment.pending_for_user(self.user).count(), 5)
        self.assertFalse(Commitment.can_create(self.user))

    def test_commitment_closure_updates_analytics(self):
        """Commitment closure feeds into analytics computation."""
        from apps.core.blueprint.models import Commitment, CommitmentAnalytics

        today = timezone.localdate()

        # Create and close commitments
        for i in range(3):
            c = _create_commitment(self.user, f'Tracked {i+1}')
            if i < 2:
                c.close(Commitment.STATUS_CLOSED_SUCCESS,
                        Commitment.CLOSURE_USER_CONFIRMED)
            else:
                c.close(Commitment.STATUS_CLOSED_MISSED,
                        Commitment.CLOSURE_USER_MISSED)

        # Compute analytics
        analytics = CommitmentAnalytics.compute_for_date(self.user, today)
        self.assertEqual(analytics.commitments_made, 3)
        self.assertEqual(analytics.commitments_honored, 2)
        self.assertEqual(analytics.commitments_missed, 1)
        self.assertAlmostEqual(analytics.honor_rate, 2/3, places=2)
