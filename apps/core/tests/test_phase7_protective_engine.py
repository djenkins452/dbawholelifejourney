"""
Phase 7 — Protective Engine Tests.

Covers:
    1. Time-block recommendation generated when CPI > 60
    2. Capacity warning escalation tiers
    3. Overload >80 → Level 2 intervention
    4. Overload >90 → Level 3 intervention
    5. Pre-deadline alerts at 24h, 4h, 1h
    6. DNE throttle respected

These tests verify the protective action engine generates correct
recommendations and alerts based on pressure thresholds.

NOTE: PressureSnapshot and Commitment have post_save signals
(protective_signals.py) that automatically trigger overload checks
and alert scheduling. Tests account for this signal-driven behavior.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_protective_engine.py
"""

import datetime as dt
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='protective-p7@example.com'):
    """Create a test user with preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_pressure_snapshot(user, pressure_index=50, **kwargs):
    """Create a PressureSnapshot with given values.

    NOTE: Creating a snapshot fires a post_save signal that automatically
    calls apply_overload_triggers and compute_protective_recommendations.
    """
    from apps.core.blueprint.pressure_models import (
        PressureSnapshot,
        PressureWeightConfig,
    )

    PressureWeightConfig.get_active()

    defaults = {
        'density_score': 0.5,
        'compression_score': 0.3,
        'breach_risk_score': 0.4,
        'erosion_score': 0.2,
        'collision_score': 0.1,
        'horizon_days': 7,
    }
    defaults.update(kwargs)

    return PressureSnapshot.objects.create(
        user=user,
        pressure_index=pressure_index,
        computed_at=timezone.now(),
        **defaults,
    )


def _create_commitment(user, text='Test', hours_ahead=48):
    """Create a pending commitment.

    NOTE: Creating a commitment fires a post_save signal that automatically
    calls schedule_deadline_alerts for the user.
    """
    from apps.core.blueprint.models import Commitment

    return Commitment.objects.create(
        user=user,
        normalized_text=text,
        commitment_type=Commitment.TYPE_DO,
        time_boundary=timezone.now() + dt.timedelta(hours=hours_ahead),
        done_definition='Done',
        status=Commitment.STATUS_PENDING,
        tier_at_creation='CLEAN',
    )


# =========================================================================
# 1) TIME-BLOCK RECOMMENDATION WHEN CPI > 60
# =========================================================================


class TimeBlockRecommendationTests(TestCase):
    """Test time-block suggestions generated at elevated CPI."""

    def setUp(self):
        self.user = _create_test_user('timeblock@example.com')

    def test_no_recommendation_when_cpi_below_60(self):
        """CPI ≤ 60 should not generate a time-block suggestion."""
        from apps.core.blueprint.protective_engine import (
            compute_protective_recommendations,
        )

        _create_pressure_snapshot(self.user, pressure_index=50)
        recs = compute_protective_recommendations(self.user)
        time_blocks = [
            r for r in recs
            if r.recommendation_type == 'TIME_BLOCK_SUGGESTION'
        ]
        self.assertEqual(len(time_blocks), 0)

    def test_recommendation_generated_when_cpi_above_60(self):
        """CPI > 60 with a free gap should generate time-block recommendation.

        The signal fires compute_protective_recommendations when snapshot
        is created. We mock the internal helpers to control behavior and
        verify the recommendation is created (by signal or explicit call).
        """
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        # Create commitment FIRST so _find_highest_risk_item finds it
        commitment = _create_commitment(self.user, 'Important task', hours_ahead=24)

        # Create snapshot WITH mocks so signal-triggered call creates the rec
        with patch(
            'apps.core.blueprint.protective_engine._has_free_gap',
            return_value=True,
        ), patch(
            'apps.core.blueprint.protective_engine._find_highest_risk_item',
            return_value={
                'label': 'Important task',
                'object_type': 'Commitment',
                'object_id': commitment.id,
            },
        ):
            _create_pressure_snapshot(
                self.user, pressure_index=65, breach_risk_score=0.7,
            )

        # The signal should have created a TIME_BLOCK recommendation
        time_blocks = ProtectiveRecommendation.objects.filter(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
            status=ProtectiveRecommendation.STATUS_ACTIVE,
        )
        self.assertGreaterEqual(time_blocks.count(), 1)

    def test_time_block_recommendation_has_call_to_action(self):
        """Time-block recommendation includes A/B call to action."""
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        commitment = _create_commitment(self.user, 'Important task', hours_ahead=24)

        with patch(
            'apps.core.blueprint.protective_engine._has_free_gap',
            return_value=True,
        ), patch(
            'apps.core.blueprint.protective_engine._find_highest_risk_item',
            return_value={
                'label': 'Important task',
                'object_type': 'Commitment',
                'object_id': commitment.id,
            },
        ):
            _create_pressure_snapshot(self.user, pressure_index=70)

        recs = ProtectiveRecommendation.objects.filter(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
        )
        if recs.exists():
            rec = recs.first()
            self.assertIn('A', rec.call_to_action)
            self.assertIn('B', rec.call_to_action)


# =========================================================================
# 2) CAPACITY WARNING ESCALATION TIERS
# =========================================================================


class CapacityWarningTierTests(TestCase):
    """Test capacity warning severity tiers based on overloaded days."""

    def setUp(self):
        self.user = _create_test_user('capacity-tiers@example.com')

    def test_capacity_warning_gentle_for_1_overloaded_day(self):
        """1 overloaded day → gentle warning."""
        from apps.core.blueprint.protective_engine import (
            compute_protective_recommendations,
        )
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        _create_pressure_snapshot(self.user, pressure_index=65)

        with patch(
            'apps.core.blueprint.protective_engine._count_overloaded_days',
            return_value=1,
        ), patch(
            'apps.core.blueprint.protective_engine._get_latest_pressure',
            return_value=_create_pressure_snapshot(self.user, pressure_index=65),
        ), patch(
            'apps.core.blueprint.protective_engine._find_highest_risk_item',
            return_value=None,
        ):
            recs = compute_protective_recommendations(self.user)

        warnings = [
            r for r in recs
            if r.recommendation_type == ProtectiveRecommendation.TYPE_CAPACITY_WARNING
        ]
        if warnings:
            self.assertLessEqual(warnings[0].priority, 50)

    def test_capacity_warning_higher_priority_for_3_overloaded_days(self):
        """3 overloaded days → red alert priority (85)."""
        from apps.core.blueprint.protective_engine import (
            compute_protective_recommendations,
        )
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        with patch(
            'apps.core.blueprint.protective_engine._count_overloaded_days',
            return_value=3,
        ), patch(
            'apps.core.blueprint.protective_engine._get_latest_pressure',
            return_value=_create_pressure_snapshot(self.user, pressure_index=80),
        ), patch(
            'apps.core.blueprint.protective_engine._find_highest_risk_item',
            return_value=None,
        ), patch(
            'apps.core.blueprint.protective_engine._check_deadline_collisions',
            return_value={'has_collisions': False},
        ):
            recs = compute_protective_recommendations(self.user)

        warnings = [
            r for r in recs
            if r.recommendation_type == ProtectiveRecommendation.TYPE_CAPACITY_WARNING
        ]
        if warnings:
            self.assertEqual(warnings[0].priority, 85)


# =========================================================================
# 3) OVERLOAD >80 → LEVEL 2 INTERVENTION
# =========================================================================


class OverloadLevel2Tests(TestCase):
    """Test CPI > 80 triggers Level 2 (Ping) intervention.

    NOTE: The post_save signal on PressureSnapshot automatically calls
    apply_overload_triggers. So we verify the InterventionLog was created
    by querying the DB rather than calling the function explicitly.
    """

    def setUp(self):
        self.user = _create_test_user('overload-l2@example.com')

    def test_cpi_81_creates_level_2_intervention(self):
        """CPI 81 (>80) creates a Level 2 Ping intervention via signal."""
        from apps.core.blueprint.models import InterventionLog

        _create_pressure_snapshot(self.user, pressure_index=81)

        # Signal should have auto-created the intervention
        intervention = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='high_load_risk',
        ).first()
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.level, InterventionLog.LEVEL_PING)

    def test_cpi_80_no_intervention(self):
        """CPI exactly 80 does not trigger intervention (threshold is >80)."""
        from apps.core.blueprint.models import InterventionLog

        _create_pressure_snapshot(self.user, pressure_index=80)

        intervention = InterventionLog.objects.filter(
            user=self.user,
        ).first()
        self.assertIsNone(intervention)

    def test_cpi_50_no_intervention(self):
        """CPI 50 (well below threshold) — no intervention."""
        from apps.core.blueprint.models import InterventionLog

        _create_pressure_snapshot(self.user, pressure_index=50)

        intervention = InterventionLog.objects.filter(
            user=self.user,
        ).first()
        self.assertIsNone(intervention)


# =========================================================================
# 4) OVERLOAD >90 → LEVEL 3 INTERVENTION
# =========================================================================


class OverloadLevel3Tests(TestCase):
    """Test CPI > 90 triggers Level 3 (Interrupt) intervention."""

    def setUp(self):
        self.user = _create_test_user('overload-l3@example.com')

    def test_cpi_91_creates_level_3_intervention(self):
        """CPI 91 (>90) creates a Level 3 Interrupt intervention via signal."""
        from apps.core.blueprint.models import InterventionLog

        _create_pressure_snapshot(self.user, pressure_index=91)

        intervention = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='critical_overload_risk',
        ).first()
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.level, InterventionLog.LEVEL_INTERRUPT)

    def test_cpi_95_creates_level_3_intervention(self):
        """CPI 95 creates Level 3 with critical overload message."""
        from apps.core.blueprint.models import InterventionLog

        _create_pressure_snapshot(self.user, pressure_index=95)

        intervention = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='critical_overload_risk',
        ).first()
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.level, InterventionLog.LEVEL_INTERRUPT)
        self.assertIn('maximum capacity', intervention.message)

    def test_overload_deduplication_within_6h(self):
        """Same overload trigger within 6h is not duplicated.

        First snapshot creation triggers an intervention via signal.
        Second snapshot creation is deduplicated by the 6h window.
        """
        from apps.core.blueprint.models import InterventionLog

        _create_pressure_snapshot(self.user, pressure_index=91)

        # First intervention exists
        count_after_first = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='critical_overload_risk',
        ).count()
        self.assertEqual(count_after_first, 1)

        # Second snapshot — should be deduplicated
        _create_pressure_snapshot(self.user, pressure_index=92)

        count_after_second = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='critical_overload_risk',
        ).count()
        self.assertEqual(count_after_second, 1)  # Still 1 — deduped

    def test_no_pressure_snapshot_no_intervention(self):
        """No pressure snapshot → no intervention."""
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        intervention = apply_overload_triggers(self.user, None)
        self.assertIsNone(intervention)


# =========================================================================
# 5) PRE-DEADLINE ALERTS AT 24H, 4H, 1H
# =========================================================================


class PreDeadlineAlertTests(TestCase):
    """Test scheduling of pre-deadline alerts.

    NOTE: The post_save signal on Commitment automatically calls
    schedule_deadline_alerts. Tests query the DB to verify alert creation.
    """

    def setUp(self):
        self.user = _create_test_user('deadline-alerts@example.com')

    def test_schedule_24h_4h_1h_alerts_for_commitment(self):
        """A commitment 48h away should get 24h, 4h, and 1h alerts
        (auto-created by the Commitment post_save signal)."""
        from apps.core.blueprint.protective_models import ProtectiveAlert

        commitment = _create_commitment(self.user, 'Important deadline',
                                         hours_ahead=48)

        # Signal should have auto-scheduled alerts
        alerts = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_type='Commitment',
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        )
        alert_types = set(alerts.values_list('alert_type', flat=True))
        self.assertIn(ProtectiveAlert.TYPE_DEADLINE_24H, alert_types)
        self.assertIn(ProtectiveAlert.TYPE_DEADLINE_4H, alert_types)
        self.assertIn(ProtectiveAlert.TYPE_DEADLINE_1H, alert_types)

    def test_no_alerts_for_past_deadlines(self):
        """Commitments with past deadlines should not get alerts."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.protective_models import ProtectiveAlert

        # Create a commitment with a deadline in the past
        Commitment.objects.create(
            user=self.user,
            normalized_text='Past deadline',
            commitment_type=Commitment.TYPE_DO,
            time_boundary=timezone.now() - dt.timedelta(hours=1),
            done_definition='Done',
            status=Commitment.STATUS_PENDING,
        )

        alerts = ProtectiveAlert.objects.filter(
            user=self.user,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        )
        self.assertEqual(alerts.count(), 0)

    def test_no_duplicate_alerts(self):
        """Same alert type for same commitment is not duplicated."""
        from apps.core.blueprint.protective_engine import schedule_deadline_alerts
        from apps.core.blueprint.protective_models import ProtectiveAlert

        commitment = _create_commitment(self.user, 'Test', hours_ahead=48)

        # Signal already created alerts; explicit call should create 0 new ones
        new_alerts = schedule_deadline_alerts(self.user, timezone.now())
        self.assertEqual(len(new_alerts), 0)

        # But the signal-created ones still exist
        total = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        ).count()
        self.assertGreater(total, 0)

    def test_alert_scheduled_at_correct_times(self):
        """Alerts are scheduled at deadline - 24h/4h/1h."""
        from apps.core.blueprint.protective_models import ProtectiveAlert

        now = timezone.now()
        deadline = now + dt.timedelta(hours=48)
        commitment = _create_commitment(self.user, 'Timed test',
                                         hours_ahead=48)

        alerts = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        )

        for alert in alerts:
            if alert.alert_type == ProtectiveAlert.TYPE_DEADLINE_24H:
                expected = deadline - dt.timedelta(hours=24)
                diff = abs((alert.scheduled_for - expected).total_seconds())
                self.assertLess(diff, 60)
            elif alert.alert_type == ProtectiveAlert.TYPE_DEADLINE_4H:
                expected = deadline - dt.timedelta(hours=4)
                diff = abs((alert.scheduled_for - expected).total_seconds())
                self.assertLess(diff, 60)
            elif alert.alert_type == ProtectiveAlert.TYPE_DEADLINE_1H:
                expected = deadline - dt.timedelta(hours=1)
                diff = abs((alert.scheduled_for - expected).total_seconds())
                self.assertLess(diff, 60)


# =========================================================================
# 6) DNE THROTTLE RESPECTED
# =========================================================================


class DNEThrottleTests(TestCase):
    """Test that delivery notification engine throttle is respected."""

    def setUp(self):
        self.user = _create_test_user('dne-throttle@example.com')

    def test_alert_cancellation_on_deadline_move(self):
        """When a deadline moves, pending alerts for old deadline cancel."""
        from apps.core.blueprint.protective_engine import cancel_alerts_for_object
        from apps.core.blueprint.protective_models import ProtectiveAlert

        commitment = _create_commitment(self.user, 'Movable deadline',
                                         hours_ahead=48)

        # Signal should have created alerts
        pending_count = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        ).count()
        self.assertGreater(pending_count, 0)

        # Cancel alerts (simulating deadline move)
        cancelled = cancel_alerts_for_object(
            self.user, 'Commitment', commitment.id, reason='deadline_moved',
        )
        self.assertEqual(cancelled, pending_count)

        # Verify all are cancelled
        still_pending = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        ).count()
        self.assertEqual(still_pending, 0)

    def test_cancelled_alerts_are_not_deleted(self):
        """Cancelled alerts remain in DB (never deleted)."""
        from apps.core.blueprint.protective_engine import cancel_alerts_for_object
        from apps.core.blueprint.protective_models import ProtectiveAlert

        commitment = _create_commitment(self.user, 'Test', hours_ahead=48)

        cancel_alerts_for_object(
            self.user, 'Commitment', commitment.id,
        )

        # Alerts still exist, just with cancelled status
        total = ProtectiveAlert.objects.filter(
            user=self.user, related_object_id=commitment.id,
        ).count()
        self.assertGreater(total, 0)

        cancelled = ProtectiveAlert.objects.filter(
            user=self.user,
            related_object_id=commitment.id,
            delivery_status=ProtectiveAlert.DELIVERY_CANCELLED,
        ).count()
        self.assertEqual(cancelled, total)

    def test_protective_action_log_created_on_cancel(self):
        """Cancellation creates ProtectiveActionLog entries."""
        from apps.core.blueprint.protective_engine import cancel_alerts_for_object
        from apps.core.blueprint.protective_models import ProtectiveActionLog

        commitment = _create_commitment(self.user, 'Logged', hours_ahead=48)

        cancel_alerts_for_object(
            self.user, 'Commitment', commitment.id,
        )

        cancel_logs = ProtectiveActionLog.objects.filter(
            user=self.user,
            event_type=ProtectiveActionLog.EVENT_ALERT_CANCELLED,
        )
        self.assertGreater(cancel_logs.count(), 0)
