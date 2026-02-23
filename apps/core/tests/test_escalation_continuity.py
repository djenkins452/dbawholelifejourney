"""
Phase 3 — Escalation Continuity Tests

Tests:
1. Escalation persists across sessions (floor behavior).
2. Immediate escalation up.
3. Slow downgrade only when all 5 criteria met.
4. Any single unmet criterion blocks downgrade.
5. Threshold override supremacy.
6. BehavioralTrend deterministic output.
7. EscalationEvent audit trail.
8. Daily update correctness.
"""

import datetime

from django.test import TestCase
from django.utils import timezone
from zoneinfo import ZoneInfo


class EscalationPersistenceTests(TestCase):
    """Escalation persists across sessions — floor behavior."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-persist@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_floor_prevents_silent_downgrade_to_clean(self):
        """
        EscalationState at level 2 (STRUCTURAL_DRIFT). Computed state is CLEAN.
        Result must NOT drop to CLEAN without recovery eligibility.
        """
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        # Set up elevated escalation state
        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_STRUCTURAL_DRIFT,
            peak_level_7d=EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        # Trajectory signals that would compute CLEAN
        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, clean_signals, '')
        self.assertNotEqual(result, 'CLEAN')
        self.assertEqual(result, 'STRUCTURAL_DRIFT')

    def test_floor_prevents_downgrade_from_early_erosion(self):
        """Level 1 (EARLY_EROSION) stays when computed is CLEAN."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_EARLY_EROSION,
            peak_level_7d=EscalationState.LEVEL_EARLY_EROSION,
        )

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, clean_signals, '')
        self.assertEqual(result, 'EARLY_EROSION')

    def test_new_user_starts_clean(self):
        """User with no EscalationState defaults to CLEAN."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, clean_signals, '')
        self.assertEqual(result, 'CLEAN')


class ImmediateEscalationTests(TestCase):
    """Escalation increases immediately when thresholds demand."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-up@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_escalation_from_clean_to_structural(self):
        """CLEAN → STRUCTURAL_DRIFT on threshold override."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationEvent, EscalationState

        # Start at CLEAN
        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        # Signals that trigger STRUCTURAL_DRIFT
        structural_signals = {
            'renegotiation_patterns': ['PRAYER'],  # ≥3 renegotiations
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, structural_signals, '')
        self.assertEqual(result, 'STRUCTURAL_DRIFT')

        # Verify event was created
        event = EscalationEvent.objects.filter(user=self.user).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.from_level, 0)
        self.assertEqual(event.to_level, 2)
        self.assertEqual(event.trigger, 'THRESHOLD_OVERRIDE')

    def test_escalation_from_early_to_structural(self):
        """EARLY_EROSION → STRUCTURAL_DRIFT on threshold override."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_EARLY_EROSION,
        )

        structural_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': ['PRAYER'],  # ≥2 Tier 1 skips
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, structural_signals, '')
        self.assertEqual(result, 'STRUCTURAL_DRIFT')

    def test_escalation_clean_to_early_on_erosion_markers(self):
        """CLEAN → EARLY_EROSION on erosion markers in user input."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(
            self.user, clean_signals, "it's not a big deal"
        )
        self.assertEqual(result, 'EARLY_EROSION')


class SlowDowngradeTests(TestCase):
    """De-escalation only when all 5 recovery criteria met."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-down@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def _setup_full_recovery(self, level=2):
        """
        Create EscalationState at given level and ensure all 5 recovery
        criteria are met: 7 clean days, >=3 honored commitments, 0 Tier1
        misses, 0 blocked renegotiations, 0 drift events in window.
        """
        from apps.core.blueprint.models import Commitment, EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=level,
            peak_level_7d=level,
        )

        # Create 3 honored commitments in the last 7 days
        now = timezone.now()
        for i in range(3):
            c = Commitment.objects.create(
                user=self.user,
                normalized_text=f'Honored commitment {i}',
                commitment_type='DO',
                time_boundary=now - datetime.timedelta(days=i + 1),
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )
            # Force updated_at into window
            Commitment.objects.filter(pk=c.pk).update(
                updated_at=now - datetime.timedelta(days=i + 1)
            )

    def test_downgrade_by_one_level_when_all_criteria_met(self):
        """Level 2 → Level 1 when all 5 criteria are met."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationEvent

        self._setup_full_recovery(level=2)

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, clean_signals, '')
        self.assertEqual(result, 'EARLY_EROSION')  # Dropped by 1: 2 → 1

        # Verify event
        event = EscalationEvent.objects.filter(
            user=self.user, trigger='RECOVERY_DECAY'
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.from_level, 2)
        self.assertEqual(event.to_level, 1)

    def test_downgrade_only_by_one_not_multiple(self):
        """Level 2 drops to 1, not straight to 0."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state

        self._setup_full_recovery(level=2)

        clean_signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, clean_signals, '')
        # Must be EARLY_EROSION (level 1), not CLEAN (level 0)
        self.assertEqual(result, 'EARLY_EROSION')


class SingleCriterionBlocksDowngradeTests(TestCase):
    """Any single unmet criterion blocks downgrade."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-block@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def _create_elevated_state(self):
        from apps.core.blueprint.models import EscalationState

        return EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_STRUCTURAL_DRIFT,
            peak_level_7d=EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

    def test_drift_event_blocks_downgrade(self):
        """Drift event in window blocks recovery."""
        from apps.core.blueprint.escalation_engine import compute_recovery_eligibility
        from apps.core.blueprint.models import DriftEvent

        self._create_elevated_state()

        # Create a drift event 2 days ago
        DriftEvent.objects.create(
            user=self.user,
            date=timezone.now().date() - datetime.timedelta(days=2),
            drift_type='FAST_BREAK_EARLY',
            behavior_key='FASTING',
            tier=2,
            pillar='HEALTH_DISCIPLINE',
            severity=0.6,
            description='Broke fast early',
            evidence={},
            occurred_at=timezone.now() - datetime.timedelta(days=2),
        )

        eligible, reasons = compute_recovery_eligibility(self.user)
        self.assertFalse(eligible)
        self.assertFalse(reasons['criteria']['zero_drift_events_met'])

    def test_insufficient_honored_commitments_blocks(self):
        """Fewer than 3 honored commitments blocks recovery."""
        from apps.core.blueprint.escalation_engine import compute_recovery_eligibility
        from apps.core.blueprint.models import Commitment

        self._create_elevated_state()

        # Only 2 honored commitments (need 3)
        now = timezone.now()
        for i in range(2):
            c = Commitment.objects.create(
                user=self.user,
                normalized_text=f'C {i}',
                commitment_type='DO',
                time_boundary=now,
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )
            Commitment.objects.filter(pk=c.pk).update(
                updated_at=now - datetime.timedelta(days=i + 1)
            )

        eligible, reasons = compute_recovery_eligibility(self.user)
        self.assertFalse(eligible)
        self.assertFalse(reasons['criteria']['honored_commitments_met'])

    def test_tier1_miss_blocks_downgrade(self):
        """Tier 1 miss in window blocks recovery."""
        from apps.core.blueprint.escalation_engine import compute_recovery_eligibility
        from apps.core.blueprint.models import DriftEvent

        self._create_elevated_state()

        # Tier 1 miss
        DriftEvent.objects.create(
            user=self.user,
            date=timezone.now().date() - datetime.timedelta(days=1),
            drift_type='FAITH_BLOCK_MISSED',
            behavior_key='PRAYER',
            tier=1,
            pillar='FAITH',
            severity=0.5,
            description='Missed morning prayer',
            evidence={},
            occurred_at=timezone.now() - datetime.timedelta(days=1),
        )

        eligible, reasons = compute_recovery_eligibility(self.user)
        self.assertFalse(eligible)
        self.assertFalse(reasons['criteria']['zero_tier1_misses_met'])

    def test_blocked_renegotiation_blocks_downgrade(self):
        """Blocked renegotiation in window blocks recovery."""
        from apps.core.blueprint.escalation_engine import compute_recovery_eligibility
        from apps.core.blueprint.models import Commitment, CommitmentRenegotiation

        self._create_elevated_state()

        # Create a blocked renegotiation
        commitment = Commitment.objects.create(
            user=self.user,
            normalized_text='Test commitment',
            commitment_type='DO',
            time_boundary=timezone.now(),
            status=Commitment.STATUS_PENDING,
        )
        CommitmentRenegotiation.objects.create(
            commitment=commitment,
            original_time_boundary=timezone.now(),
            tier_at_time='STRUCTURAL_DRIFT',
            was_blocked=True,
        )

        eligible, reasons = compute_recovery_eligibility(self.user)
        self.assertFalse(eligible)
        self.assertFalse(reasons['criteria']['zero_blocked_renegotiations_met'])


class ThresholdOverrideSupremacyTests(TestCase):
    """Threshold override always escalates, even if recovery eligible."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-override@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_threshold_overrides_recovery_eligible(self):
        """
        Even with all 5 recovery criteria met, structural drift thresholds
        still escalate immediately.
        """
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import Commitment, EscalationState

        # Start at level 1, with full recovery conditions
        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_EARLY_EROSION,
        )

        # 3 honored commitments
        now = timezone.now()
        for i in range(3):
            c = Commitment.objects.create(
                user=self.user,
                normalized_text=f'C {i}',
                commitment_type='DO',
                time_boundary=now,
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )
            Commitment.objects.filter(pk=c.pk).update(
                updated_at=now - datetime.timedelta(days=i + 1)
            )

        # But trajectory signals say STRUCTURAL_DRIFT
        structural_signals = {
            'renegotiation_patterns': ['PRAYER'],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        result = resolve_activation_state(self.user, structural_signals, '')
        # Threshold override: MUST escalate to STRUCTURAL_DRIFT
        self.assertEqual(result, 'STRUCTURAL_DRIFT')

    def test_consecutive_tier1_skips_escalate(self):
        """Consecutive Tier 1 skips trigger immediate escalation."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        signals = {
            'renegotiation_patterns': [],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 3,
        }

        result = resolve_activation_state(self.user, signals, '')
        self.assertEqual(result, 'STRUCTURAL_DRIFT')


class BehavioralTrendTests(TestCase):
    """BehavioralTrend deterministic output."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='trend-test@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_declining_trend_when_drift_increases(self):
        """More drift events in current window → declining trend."""
        from apps.core.blueprint.escalation_engine import compute_behavioral_trends
        from apps.core.blueprint.models import DriftEvent

        now = timezone.now()

        # Prior window: 1 drift event
        DriftEvent.objects.create(
            user=self.user,
            date=(now - datetime.timedelta(days=10)).date(),
            drift_type='WORKOUT_SKIPPED',
            behavior_key='WORKOUT',
            tier=2,
            pillar='HEALTH_DISCIPLINE',
            severity=0.5,
            description='Skipped workout',
            evidence={},
            occurred_at=now - datetime.timedelta(days=10),
        )

        # Current window: 3 drift events
        for i in range(3):
            DriftEvent.objects.create(
                user=self.user,
                date=(now - datetime.timedelta(days=i + 1)).date(),
                drift_type='WORKOUT_SKIPPED',
                behavior_key='WORKOUT',
                tier=2,
                pillar='HEALTH_DISCIPLINE',
                severity=0.5,
                description=f'Skipped workout {i}',
                evidence={},
                occurred_at=now - datetime.timedelta(days=i + 1),
            )

        trends = compute_behavioral_trends(self.user, now)
        workout_trend = next(
            (t for t in trends if t.behavior_key == 'WORKOUT'), None
        )
        self.assertIsNotNone(workout_trend)
        self.assertEqual(workout_trend.trend_direction, 'declining')

    def test_improving_trend_when_drift_decreases(self):
        """Fewer drift events in current window → improving trend."""
        from apps.core.blueprint.escalation_engine import compute_behavioral_trends
        from apps.core.blueprint.models import DriftEvent

        now = timezone.now()

        # Prior window: 3 drift events
        for i in range(3):
            DriftEvent.objects.create(
                user=self.user,
                date=(now - datetime.timedelta(days=10 + i)).date(),
                drift_type='FAITH_BLOCK_MISSED',
                behavior_key='PRAYER',
                tier=1,
                pillar='FAITH',
                severity=0.5,
                description=f'Missed prayer {i}',
                evidence={},
                occurred_at=now - datetime.timedelta(days=10 + i),
            )

        # Current window: 1 drift event
        DriftEvent.objects.create(
            user=self.user,
            date=(now - datetime.timedelta(days=2)).date(),
            drift_type='FAITH_BLOCK_MISSED',
            behavior_key='PRAYER',
            tier=1,
            pillar='FAITH',
            severity=0.5,
            description='Missed prayer recent',
            evidence={},
            occurred_at=now - datetime.timedelta(days=2),
        )

        trends = compute_behavioral_trends(self.user, now)
        prayer_trend = next(
            (t for t in trends if t.behavior_key == 'PRAYER'), None
        )
        self.assertIsNotNone(prayer_trend)
        self.assertEqual(prayer_trend.trend_direction, 'improving')

    def test_stable_trend_when_no_change(self):
        """No drift events → stable trend for 'overall'."""
        from apps.core.blueprint.escalation_engine import compute_behavioral_trends

        now = timezone.now()
        trends = compute_behavioral_trends(self.user, now)

        self.assertEqual(len(trends), 1)
        self.assertEqual(trends[0].behavior_key, 'overall')
        self.assertEqual(trends[0].trend_direction, 'stable')

    def test_confidence_scales_with_data_points(self):
        """Confidence = min(1.0, data_points / 20)."""
        from apps.core.blueprint.escalation_engine import compute_behavioral_trends
        from apps.core.blueprint.models import DriftEvent

        now = timezone.now()

        # 5 drift events total
        for i in range(5):
            DriftEvent.objects.create(
                user=self.user,
                date=(now - datetime.timedelta(days=i + 1)).date(),
                drift_type='GOAL_SLIP',
                behavior_key='GOALS',
                tier=3,
                pillar='PURPOSE',
                severity=0.4,
                description=f'Goal slip {i}',
                evidence={},
                occurred_at=now - datetime.timedelta(days=i + 1),
            )

        trends = compute_behavioral_trends(self.user, now)
        goals_trend = next(
            (t for t in trends if t.behavior_key == 'GOALS'), None
        )
        self.assertIsNotNone(goals_trend)
        self.assertEqual(goals_trend.confidence, 5 / 20.0)


class EscalationEventAuditTests(TestCase):
    """EscalationEvent audit trail correctness."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='esc-audit@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_escalation_creates_event(self):
        """Escalation up creates an EscalationEvent."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationEvent, EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_CLEAN,
        )

        signals = {
            'renegotiation_patterns': ['X'],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        resolve_activation_state(self.user, signals, '')

        events = EscalationEvent.objects.filter(user=self.user)
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.from_level, 0)
        self.assertEqual(event.to_level, 2)
        self.assertIn('computed_state', event.rationale)

    def test_no_event_when_level_unchanged(self):
        """No EscalationEvent when computed equals current."""
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        from apps.core.blueprint.models import EscalationEvent, EscalationState

        EscalationState.objects.create(
            user=self.user,
            current_level=EscalationState.LEVEL_STRUCTURAL_DRIFT,
        )

        # Signals still compute STRUCTURAL_DRIFT
        signals = {
            'renegotiation_patterns': ['X'],
            'tier1_skip_patterns': [],
            'consecutive_tier1_skips': 0,
        }

        resolve_activation_state(self.user, signals, '')

        events = EscalationEvent.objects.filter(user=self.user)
        self.assertEqual(events.count(), 0)


class DailyUpdateTests(TestCase):
    """Daily escalation state update correctness."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='daily-update@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_consecutive_clean_days_computed(self):
        """Daily update correctly counts consecutive clean days."""
        from apps.core.blueprint.escalation_engine import update_daily_escalation_state
        from apps.core.blueprint.models import EscalationState

        # No drift events → should have clean days
        update_daily_escalation_state(self.user)

        state = EscalationState.objects.get(user=self.user)
        # With no drift events ever, all days are clean
        self.assertGreater(state.consecutive_clean_days, 0)

    def test_drift_event_resets_clean_streak(self):
        """Drift event yesterday breaks the clean streak."""
        from apps.core.blueprint.escalation_engine import update_daily_escalation_state
        from apps.core.blueprint.models import DriftEvent, EscalationState

        now = timezone.now()

        # Drift event yesterday
        DriftEvent.objects.create(
            user=self.user,
            date=(now - datetime.timedelta(days=1)).date(),
            drift_type='WORKOUT_SKIPPED',
            behavior_key='WORKOUT',
            tier=2,
            pillar='HEALTH_DISCIPLINE',
            severity=0.5,
            description='Skipped workout',
            evidence={},
            occurred_at=now - datetime.timedelta(days=1),
        )

        update_daily_escalation_state(self.user)

        state = EscalationState.objects.get(user=self.user)
        self.assertEqual(state.consecutive_clean_days, 0)


class RecoveryEligibilityTests(TestCase):
    """Detailed recovery eligibility computation."""

    def setUp(self):
        from apps.users.models import User, UserPreferences

        self.user = User.objects.create_user(
            email='recovery-elig@example.com',
            password='testpass123',
        )
        UserPreferences.objects.get_or_create(
            user=self.user,
            defaults={'timezone': 'America/New_York'},
        )

    def test_all_criteria_met_returns_eligible(self):
        """Perfect 7-day window → eligible for de-escalation."""
        from apps.core.blueprint.escalation_engine import compute_recovery_eligibility
        from apps.core.blueprint.models import Commitment

        now = timezone.now()

        # 3 honored commitments
        for i in range(3):
            c = Commitment.objects.create(
                user=self.user,
                normalized_text=f'Good commitment {i}',
                commitment_type='DO',
                time_boundary=now,
                status=Commitment.STATUS_CLOSED_SUCCESS,
            )
            Commitment.objects.filter(pk=c.pk).update(
                updated_at=now - datetime.timedelta(days=i + 1)
            )

        eligible, reasons = compute_recovery_eligibility(self.user, now)
        self.assertTrue(eligible)
        self.assertTrue(all(reasons['criteria'].values()))

    def test_reasons_dict_is_comprehensive(self):
        """Reasons dict contains all expected keys."""
        from apps.core.blueprint.escalation_engine import compute_recovery_eligibility

        _, reasons = compute_recovery_eligibility(self.user)

        self.assertIn('drift_events_in_window', reasons)
        self.assertIn('honored_commitments', reasons)
        self.assertIn('tier1_misses', reasons)
        self.assertIn('blocked_renegotiations', reasons)
        self.assertIn('consecutive_clean_days', reasons)
        self.assertIn('eligible', reasons)
        self.assertIn('criteria', reasons)
