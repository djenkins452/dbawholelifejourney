"""
Phase 7 — Escalation Continuity Tests.

Covers:
    1. STRUCTURAL_DRIFT persists across new conversation
    2. Single positive message does not downgrade
    3. Hybrid Recovery Rule requires all 5 criteria
    4. Escalation decreases only one level at a time

These tests verify that escalation state is persistent, cross-session,
and only changes through the proper gating mechanisms.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_escalation_continuity.py
"""

import datetime as dt
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='escalation-p7@example.com'):
    """Create a test user with preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_escalation_state(user, level=0):
    """Create or update escalation state for user."""
    from apps.core.blueprint.models import EscalationState

    state, _ = EscalationState.objects.get_or_create(user=user)
    state.current_level = level
    state.save()
    return state


def _create_commitment(user, text='Test', status='pending', hours_ahead=48):
    """Create a commitment."""
    from apps.core.blueprint.models import Commitment

    return Commitment.objects.create(
        user=user,
        normalized_text=text,
        commitment_type=Commitment.TYPE_DO,
        time_boundary=timezone.now() + dt.timedelta(hours=hours_ahead),
        done_definition='Done',
        status=status,
        tier_at_creation='CLEAN',
    )


def _create_drift_event(user, days_ago=0, tier=1):
    """Create a drift event."""
    from apps.core.blueprint.models import DriftEvent

    occurred = timezone.now() - dt.timedelta(days=days_ago)
    return DriftEvent.objects.create(
        user=user,
        drift_type=DriftEvent.DRIFT_BLOCK_MISSED,
        date=occurred.date(),
        occurred_at=occurred,
        behavior_key='WORKOUT',
        tier=tier,
        severity=0.7,
    )


# =========================================================================
# 1) STRUCTURAL_DRIFT PERSISTS ACROSS CONVERSATIONS
# =========================================================================


class EscalationPersistenceTests(TestCase):
    """Test that escalation state persists across sessions/conversations."""

    def setUp(self):
        self.user = _create_test_user('persist@example.com')

    def test_structural_drift_persists_in_db(self):
        """STRUCTURAL_DRIFT level is persisted in the database."""
        from apps.core.blueprint.models import EscalationState

        state = _create_escalation_state(
            self.user, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        # Simulate "new session" by re-fetching from DB
        fresh_state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            fresh_state.current_level,
            EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

    def test_escalation_state_is_one_to_one(self):
        """Each user has exactly one EscalationState."""
        from apps.core.blueprint.models import EscalationState

        state1 = _create_escalation_state(self.user, 0)
        state2, created = EscalationState.objects.get_or_create(
            user=self.user,
        )
        self.assertFalse(created)
        self.assertEqual(state1.pk, state2.pk)

    def test_resolve_activation_state_uses_persistent_floor(self):
        """resolve_activation_state respects persistent escalation floor."""
        from apps.core.blueprint.escalation_engine import (
            ACTIVATION_STRUCTURAL_DRIFT,
            resolve_activation_state,
        )
        from apps.core.blueprint.models import EscalationState

        # Set user to STRUCTURAL_DRIFT
        _create_escalation_state(
            self.user, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        # Clean signals should not downgrade
        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(
            self.user, clean_signals, user_input='I had a great day!',
        )

        # Floor holds — still STRUCTURAL_DRIFT
        self.assertEqual(result, ACTIVATION_STRUCTURAL_DRIFT)

    def test_early_erosion_persists_across_sessions(self):
        """EARLY_EROSION level persists when re-fetched."""
        from apps.core.blueprint.models import EscalationState

        _create_escalation_state(
            self.user, EscalationState.LEVEL_EARLY_EROSION,
        )

        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            state.current_level, EscalationState.LEVEL_EARLY_EROSION,
        )


# =========================================================================
# 2) SINGLE POSITIVE MESSAGE DOES NOT DOWNGRADE
# =========================================================================


class SinglePositiveMessageNoDowngradeTests(TestCase):
    """A single positive message should not cause de-escalation."""

    def setUp(self):
        self.user = _create_test_user('no-downgrade@example.com')

    def test_positive_message_does_not_downgrade_from_structural_drift(self):
        """A positive message doesn't drop STRUCTURAL_DRIFT."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        _create_escalation_state(
            self.user, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(
            self.user, clean_signals,
            user_input='Everything is going well today!',
        )

        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            state.current_level, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

    def test_positive_message_does_not_downgrade_from_early_erosion(self):
        """A positive message doesn't drop EARLY_EROSION."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        _create_escalation_state(
            self.user, EscalationState.LEVEL_EARLY_EROSION,
        )

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(
            self.user, clean_signals,
            user_input='I feel great today!',
        )

        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            state.current_level, EscalationState.LEVEL_EARLY_EROSION,
        )


# =========================================================================
# 3) HYBRID RECOVERY RULE REQUIRES ALL 5 CRITERIA
# =========================================================================


class HybridRecoveryRuleTests(TestCase):
    """Test that de-escalation requires ALL 5 criteria."""

    def setUp(self):
        self.user = _create_test_user('recovery@example.com')

    def test_all_5_criteria_met_allows_de_escalation(self):
        """When all 5 criteria are met, de-escalation is eligible."""
        from apps.core.blueprint.escalation_engine import (
            compute_recovery_eligibility,
        )
        from apps.core.blueprint.models import Commitment

        # Create 3 honored commitments in the last 7 days
        for i in range(3):
            c = _create_commitment(
                self.user, f'Honored {i}',
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )

        now = timezone.now()
        eligible, reasons = compute_recovery_eligibility(self.user, now)

        # All criteria should be met (no drifts, no tier1 misses,
        # no blocked renegotiations, 3+ honored commitments, 7 clean days)
        self.assertTrue(eligible)
        self.assertTrue(reasons['criteria']['honored_commitments_met'])
        self.assertTrue(reasons['criteria']['zero_tier1_misses_met'])
        self.assertTrue(reasons['criteria']['zero_blocked_renegotiations_met'])
        self.assertTrue(reasons['criteria']['zero_drift_events_met'])

    def test_missing_honored_commitments_blocks_recovery(self):
        """Only 2 honored commitments (need 3) blocks recovery."""
        from apps.core.blueprint.escalation_engine import (
            compute_recovery_eligibility,
        )
        from apps.core.blueprint.models import Commitment

        for i in range(2):
            _create_commitment(
                self.user, f'Honored {i}',
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )

        eligible, reasons = compute_recovery_eligibility(
            self.user, timezone.now(),
        )

        self.assertFalse(eligible)
        self.assertFalse(reasons['criteria']['honored_commitments_met'])

    def test_tier1_miss_blocks_recovery(self):
        """A single Tier 1 drift event blocks recovery."""
        from apps.core.blueprint.escalation_engine import (
            compute_recovery_eligibility,
        )
        from apps.core.blueprint.models import Commitment

        # Create 3 honored commitments
        for i in range(3):
            _create_commitment(
                self.user, f'Honored {i}',
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )

        # Add a Tier 1 drift event in the window
        _create_drift_event(self.user, days_ago=3, tier=1)

        eligible, reasons = compute_recovery_eligibility(
            self.user, timezone.now(),
        )

        self.assertFalse(eligible)
        self.assertFalse(reasons['criteria']['zero_tier1_misses_met'])

    def test_blocked_renegotiation_blocks_recovery(self):
        """A blocked renegotiation blocks recovery."""
        from apps.core.blueprint.escalation_engine import (
            compute_recovery_eligibility,
        )
        from apps.core.blueprint.models import (
            Commitment,
            CommitmentRenegotiation,
        )

        # Create 3 honored commitments
        for i in range(3):
            _create_commitment(
                self.user, f'Honored {i}',
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )

        # Create a blocked renegotiation
        active = _create_commitment(self.user, 'Active')
        CommitmentRenegotiation.objects.create(
            commitment=active,
            original_time_boundary=active.time_boundary,
            tier_at_time='STRUCTURAL_DRIFT',
            was_blocked=True,
        )

        eligible, reasons = compute_recovery_eligibility(
            self.user, timezone.now(),
        )

        self.assertFalse(eligible)
        self.assertFalse(
            reasons['criteria']['zero_blocked_renegotiations_met'],
        )

    def test_drift_event_breaks_consecutive_clean_days(self):
        """A drift event breaks the consecutive clean days chain."""
        from apps.core.blueprint.escalation_engine import (
            compute_recovery_eligibility,
        )
        from apps.core.blueprint.models import Commitment

        for i in range(3):
            _create_commitment(
                self.user, f'Honored {i}',
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )

        # Drift event 2 days ago breaks the 7-day clean chain
        _create_drift_event(self.user, days_ago=2, tier=2)

        eligible, reasons = compute_recovery_eligibility(
            self.user, timezone.now(),
        )

        self.assertFalse(eligible)
        self.assertLess(reasons['consecutive_clean_days'], 7)


# =========================================================================
# 4) ESCALATION DECREASES ONLY ONE LEVEL AT A TIME
# =========================================================================


class EscalationOneStepDecreaseTests(TestCase):
    """Verify de-escalation drops exactly one level, not to CLEAN."""

    def setUp(self):
        self.user = _create_test_user('one-step@example.com')

    def test_structural_drift_drops_to_early_erosion_not_clean(self):
        """STRUCTURAL_DRIFT (2) → EARLY_EROSION (1), not CLEAN (0)."""
        from apps.core.blueprint.escalation_engine import (
            ACTIVATION_EARLY_EROSION,
            resolve_activation_state,
        )
        from apps.core.blueprint.models import (
            Commitment,
            EscalationState,
        )

        # Set to STRUCTURAL_DRIFT
        _create_escalation_state(
            self.user, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        # Create 3 honored commitments for recovery eligibility
        for i in range(3):
            _create_commitment(
                self.user, f'Honored {i}',
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )

        # Mock recovery eligibility to return True
        with patch(
            'apps.core.blueprint.escalation_engine.compute_recovery_eligibility',
            return_value=(True, {
                'eligible': True,
                'criteria': {
                    'consecutive_clean_days_met': True,
                    'honored_commitments_met': True,
                    'zero_tier1_misses_met': True,
                    'zero_blocked_renegotiations_met': True,
                    'zero_drift_events_met': True,
                },
            }),
        ):
            result = resolve_activation_state(
                self.user,
                {'renegotiation_patterns': [], 'tier1_skip_patterns': [],
                 'consecutive_tier1_skips': 0},
                user_input='',
            )

        self.assertEqual(result, ACTIVATION_EARLY_EROSION)

        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            state.current_level, EscalationState.LEVEL_EARLY_EROSION,
        )

    def test_early_erosion_drops_to_clean(self):
        """EARLY_EROSION (1) → CLEAN (0) with recovery gate pass."""
        from apps.core.blueprint.escalation_engine import (
            ACTIVATION_CLEAN,
            resolve_activation_state,
        )
        from apps.core.blueprint.models import EscalationState

        _create_escalation_state(
            self.user, EscalationState.LEVEL_EARLY_EROSION,
        )

        with patch(
            'apps.core.blueprint.escalation_engine.compute_recovery_eligibility',
            return_value=(True, {'eligible': True, 'criteria': {
                'consecutive_clean_days_met': True,
                'honored_commitments_met': True,
                'zero_tier1_misses_met': True,
                'zero_blocked_renegotiations_met': True,
                'zero_drift_events_met': True,
            }}),
        ):
            result = resolve_activation_state(
                self.user,
                {'renegotiation_patterns': [], 'tier1_skip_patterns': [],
                 'consecutive_tier1_skips': 0},
                user_input='',
            )

        self.assertEqual(result, ACTIVATION_CLEAN)

    def test_escalation_event_created_on_de_escalation(self):
        """De-escalation creates an EscalationEvent."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import (
            EscalationEvent,
            EscalationState,
        )

        _create_escalation_state(
            self.user, EscalationState.LEVEL_EARLY_EROSION,
        )

        with patch(
            'apps.core.blueprint.escalation_engine.compute_recovery_eligibility',
            return_value=(True, {'eligible': True, 'criteria': {
                'consecutive_clean_days_met': True,
                'honored_commitments_met': True,
                'zero_tier1_misses_met': True,
                'zero_blocked_renegotiations_met': True,
                'zero_drift_events_met': True,
            }}),
        ):
            resolve_activation_state(
                self.user,
                {'renegotiation_patterns': [], 'tier1_skip_patterns': [],
                 'consecutive_tier1_skips': 0},
                user_input='',
            )

        event = EscalationEvent.objects.filter(user=self.user).latest('created_at')
        self.assertEqual(event.from_level, 1)
        self.assertEqual(event.to_level, 0)
        self.assertEqual(event.trigger, EscalationEvent.TRIGGER_RECOVERY_DECAY)

    def test_escalation_increase_is_immediate(self):
        """Escalation increase happens immediately (no gate)."""
        from apps.core.blueprint.escalation_engine import (
            ACTIVATION_STRUCTURAL_DRIFT,
            resolve_activation_state,
        )
        from apps.core.blueprint.models import EscalationState

        _create_escalation_state(
            self.user, EscalationState.LEVEL_CLEAN,
        )

        # Signals that trigger STRUCTURAL_DRIFT
        drift_signals = {
            'renegotiation_patterns': ['blocked_reneg_1'],
            'tier1_skip_patterns': ['skip_1'],
            'consecutive_tier1_skips': 3,
        }

        result = resolve_activation_state(
            self.user, drift_signals, user_input='',
        )

        self.assertEqual(result, ACTIVATION_STRUCTURAL_DRIFT)

        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(
            state.current_level, EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

    def test_escalation_event_created_on_increase(self):
        """Escalation increase creates an EscalationEvent."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import (
            EscalationEvent,
            EscalationState,
        )

        _create_escalation_state(
            self.user, EscalationState.LEVEL_CLEAN,
        )

        drift_signals = {
            'renegotiation_patterns': ['blocked_reneg_1'],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        resolve_activation_state(self.user, drift_signals, user_input='')

        event = EscalationEvent.objects.filter(user=self.user).latest('created_at')
        self.assertEqual(event.from_level, 0)
        self.assertEqual(event.to_level, 2)
        self.assertEqual(
            event.trigger, EscalationEvent.TRIGGER_THRESHOLD_OVERRIDE,
        )
