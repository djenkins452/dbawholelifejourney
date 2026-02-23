"""
Phase 7 — Forecast & Pressure Modeling Tests.

Covers:
    1. Density scoring 0, 0.5, 1.0
    2. Compression detection
    3. Breach probability increases with density
    4. Goal erosion threshold detection
    5. Collision detection (<2h spacing)
    6. Composite CPI calculation accuracy

These tests verify the deterministic pressure engine computes all
components and the Composite Pressure Index correctly.

Project: Whole Life Journey
Path: apps/core/tests/test_phase7_forecast_pressure.py
"""

import datetime as dt
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, UserPreferences


def _create_test_user(email='pressure-p7@example.com'):
    """Create a test user with preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    UserPreferences.objects.get_or_create(
        user=user, defaults={'timezone': 'America/New_York'},
    )
    return user


def _create_active_plan_with_blocks(user, date, blocks):
    """Create an active ArchitecturePlan with ScheduledBlocks.

    Args:
        user: User instance.
        date: date for the plan.
        blocks: list of (start_time, end_time, tier) tuples.
    """
    from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock

    plan = ArchitecturePlan.objects.create(
        user=user, date=date, status=ArchitecturePlan.STATUS_ACTIVE,
    )
    for start, end, tier in blocks:
        ScheduledBlock.objects.create(
            plan=plan,
            start_time=start,
            end_time=end,
            title=f'Block {start}-{end}',
            tier=tier,
        )
    return plan


def _create_pressure_weight_config():
    """Ensure default pressure weight config exists."""
    from apps.core.blueprint.pressure_models import PressureWeightConfig
    return PressureWeightConfig.get_active()


# =========================================================================
# 1) DENSITY SCORING: 0, 0.5, 1.0
# =========================================================================


class DensityScoringTests(TestCase):
    """Test calendar density computation at key thresholds."""

    def setUp(self):
        self.user = _create_test_user('density@example.com')

    def test_density_zero_with_no_plans(self):
        """No architecture plans → density = 0.0."""
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        density = compute_calendar_density(self.user, horizon_days=7)
        self.assertEqual(density, 0.0)

    def test_density_approximately_half_with_half_day_schedule(self):
        """Scheduling ~450 min of 900 available → ~0.5 density."""
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        # Schedule 7:00-14:30 = 450 minutes (half of 900)
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(7, 0), dt.time(14, 30), 1),
        ])

        density = compute_calendar_density(self.user, horizon_days=1)
        self.assertAlmostEqual(density, 0.5, places=1)

    def test_density_one_with_fully_packed_schedule(self):
        """Scheduling all 900 minutes → density = 1.0."""
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        # Schedule 7:00-22:00 = 900 minutes
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(7, 0), dt.time(22, 0), 1),
        ])

        density = compute_calendar_density(self.user, horizon_days=1)
        self.assertAlmostEqual(density, 1.0, places=1)

    def test_density_clamped_at_1(self):
        """Even if scheduling exceeds available, density caps at 1.0."""
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        # Create overlapping blocks totaling more than 900 min
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(7, 0), dt.time(22, 0), 1),
            (dt.time(7, 0), dt.time(12, 0), 2),  # Overlap
        ])

        density = compute_calendar_density(self.user, horizon_days=1)
        self.assertLessEqual(density, 1.0)

    def test_density_across_multiple_days(self):
        """Density averaged across a 3-day horizon."""
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        # Day 1: fully packed, Day 2: empty, Day 3: half
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(7, 0), dt.time(22, 0), 1),
        ])
        _create_active_plan_with_blocks(
            self.user, today + dt.timedelta(days=2), [
                (dt.time(7, 0), dt.time(14, 30), 1),
            ],
        )

        density = compute_calendar_density(self.user, horizon_days=3)
        # Expected: (900 + 0 + 450) / (900 * 3) = 1350/2700 = 0.5
        self.assertAlmostEqual(density, 0.5, places=1)


# =========================================================================
# 2) COMPRESSION DETECTION
# =========================================================================


class CompressionDetectionTests(TestCase):
    """Test workload compression scoring."""

    def setUp(self):
        self.user = _create_test_user('compression@example.com')

    def test_no_flexible_blocks_no_compression(self):
        """No flexible (Tier 3+) blocks → compression = 0.0."""
        from apps.core.blueprint.pressure_engine import compute_compression

        today = timezone.localdate()
        # Only Tier 1 blocks
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(7, 0), dt.time(12, 0), 1),
        ])

        compression = compute_compression(self.user, horizon_days=1)
        self.assertEqual(compression, 0.0)

    def test_compression_detected_when_flexible_exceeds_threshold(self):
        """Compression > 0 when flexible blocks exceed free time × 1.2."""
        from apps.core.blueprint.pressure_engine import compute_compression

        today = timezone.localdate()
        # Packed schedule with lots of Tier 3+ blocks
        # Total: 7:00-20:00 = 780 min, leaving 120 min free
        # Flexible: Tier 3 = 300 min (12:00-17:00)
        # Free = 120 min. Threshold = 120 * 1.2 = 144
        # 300 > 144 → compression detected
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(7, 0), dt.time(12, 0), 1),   # 300 min Tier 1
            (dt.time(12, 0), dt.time(17, 0), 3),   # 300 min Tier 3 (flexible)
            (dt.time(17, 0), dt.time(20, 0), 1),   # 180 min Tier 1
        ])

        compression = compute_compression(self.user, horizon_days=1)
        self.assertGreater(compression, 0.0)

    def test_no_compression_when_schedule_is_light(self):
        """Light schedule with some Tier 3 blocks → no compression."""
        from apps.core.blueprint.pressure_engine import compute_compression

        today = timezone.localdate()
        # Only 2 hours scheduled total
        _create_active_plan_with_blocks(self.user, today, [
            (dt.time(9, 0), dt.time(10, 0), 1),
            (dt.time(14, 0), dt.time(15, 0), 3),
        ])

        compression = compute_compression(self.user, horizon_days=1)
        self.assertEqual(compression, 0.0)


# =========================================================================
# 3) BREACH PROBABILITY INCREASES WITH DENSITY
# =========================================================================


class BreachProbabilityTests(TestCase):
    """Test breach probability scoring."""

    def setUp(self):
        self.user = _create_test_user('breach@example.com')

    def test_breach_zero_with_no_overrides_or_drifts(self):
        """No overrides, no drifts → breach probability = 0.0."""
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        breach = compute_breach_probability(self.user, horizon_days=7)
        self.assertEqual(breach, 0.0)

    def test_breach_increases_with_tier1_overrides(self):
        """More Tier 1 overrides → higher breach probability."""
        from apps.core.blueprint.models import (
            ArchitecturePlan,
            ScheduledBlock,
            Tier1OverrideEvent,
        )
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        today = timezone.localdate()
        plan = ArchitecturePlan.objects.create(
            user=self.user, date=today,
            status=ArchitecturePlan.STATUS_ACTIVE,
        )
        block = ScheduledBlock.objects.create(
            plan=plan, start_time=dt.time(7, 0), end_time=dt.time(8, 0),
            title='T1 block', tier=1,
        )

        # Create 4 overrides (max score at 4)
        for _ in range(4):
            Tier1OverrideEvent.objects.create(
                user=self.user,
                original_block=block,
                conflicting_block_description='Meeting',
                escalation_level_at_time='CLEAN',
            )

        breach = compute_breach_probability(self.user, horizon_days=7)
        self.assertGreater(breach, 0.0)

    def test_breach_increases_with_tier1_drift_events(self):
        """Tier 1 drift events increase breach probability."""
        from apps.core.blueprint.models import DriftEvent
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        for i in range(3):
            DriftEvent.objects.create(
                user=self.user,
                drift_type=DriftEvent.DRIFT_WORKOUT_SKIPPED,
                date=(timezone.now() - dt.timedelta(days=i)).date(),
                occurred_at=timezone.now() - dt.timedelta(days=i),
                behavior_key='WORKOUT',
                tier=1,
                severity=0.8,
            )

        breach = compute_breach_probability(self.user, horizon_days=7)
        self.assertGreater(breach, 0.0)


# =========================================================================
# 4) GOAL EROSION THRESHOLD DETECTION
# =========================================================================


class GoalErosionTests(TestCase):
    """Test goal trajectory erosion scoring."""

    def setUp(self):
        self.user = _create_test_user('erosion@example.com')

    def test_erosion_zero_with_no_goals(self):
        """No active goals → erosion = 0.0."""
        from apps.core.blueprint.pressure_engine import compute_goal_erosion

        erosion = compute_goal_erosion(self.user, horizon_days=7)
        self.assertEqual(erosion, 0.0)

    def test_erosion_detects_past_due_goal(self):
        """A goal past its target date should score 1.0."""
        from apps.core.blueprint.pressure_engine import compute_goal_erosion

        try:
            from apps.purpose.models import LifeGoal
        except ImportError:
            self.skipTest('Purpose app not available')

        # Create a goal that's past due
        # NOTE: milestone_progress_percent is a read-only @property
        LifeGoal.objects.create(
            user=self.user,
            title='Past due goal',
            status='active',
            target_date=timezone.localdate() - dt.timedelta(days=1),
        )

        erosion = compute_goal_erosion(self.user, horizon_days=7)
        self.assertGreater(erosion, 0.0)

    def test_erosion_zero_for_distant_goals(self):
        """Goals far in the future (> 2× horizon) don't contribute."""
        from apps.core.blueprint.pressure_engine import compute_goal_erosion

        try:
            from apps.purpose.models import LifeGoal
        except ImportError:
            self.skipTest('Purpose app not available')

        # NOTE: milestone_progress_percent is a read-only @property
        LifeGoal.objects.create(
            user=self.user,
            title='Far future goal',
            status='active',
            target_date=timezone.localdate() + dt.timedelta(days=365),
        )

        erosion = compute_goal_erosion(self.user, horizon_days=7)
        self.assertEqual(erosion, 0.0)


# =========================================================================
# 5) COLLISION DETECTION (<2h SPACING)
# =========================================================================


class CollisionDetectionTests(TestCase):
    """Test deadline collision detection."""

    def setUp(self):
        self.user = _create_test_user('collision@example.com')

    def test_no_collisions_with_no_deadlines(self):
        """No commitments/goals → collision = 0.0."""
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        collision = compute_deadline_collisions(self.user, horizon_days=7)
        self.assertEqual(collision, 0.0)

    def test_collision_detected_with_less_than_2h_gap(self):
        """Two deadlines <2h apart should produce collision > 0."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        now = timezone.now()
        # Two commitments 1 hour apart
        Commitment.objects.create(
            user=self.user,
            normalized_text='Task A',
            commitment_type=Commitment.TYPE_DO,
            time_boundary=now + dt.timedelta(hours=24),
            done_definition='Done A',
            status=Commitment.STATUS_PENDING,
        )
        Commitment.objects.create(
            user=self.user,
            normalized_text='Task B',
            commitment_type=Commitment.TYPE_DO,
            time_boundary=now + dt.timedelta(hours=25),
            done_definition='Done B',
            status=Commitment.STATUS_PENDING,
        )

        collision = compute_deadline_collisions(self.user, horizon_days=7)
        self.assertGreater(collision, 0.0)

    def test_no_collision_with_wide_spacing(self):
        """Deadlines 3+ hours apart should not collide."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        now = timezone.now()
        Commitment.objects.create(
            user=self.user,
            normalized_text='Task A',
            commitment_type=Commitment.TYPE_DO,
            time_boundary=now + dt.timedelta(hours=24),
            done_definition='Done A',
            status=Commitment.STATUS_PENDING,
        )
        Commitment.objects.create(
            user=self.user,
            normalized_text='Task B',
            commitment_type=Commitment.TYPE_DO,
            time_boundary=now + dt.timedelta(hours=28),
            done_definition='Done B',
            status=Commitment.STATUS_PENDING,
        )

        collision = compute_deadline_collisions(self.user, horizon_days=7)
        self.assertEqual(collision, 0.0)

    def test_single_deadline_no_collision(self):
        """A single deadline can't collide with itself."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        Commitment.objects.create(
            user=self.user,
            normalized_text='Solo Task',
            commitment_type=Commitment.TYPE_DO,
            time_boundary=timezone.now() + dt.timedelta(hours=24),
            done_definition='Done',
            status=Commitment.STATUS_PENDING,
        )

        collision = compute_deadline_collisions(self.user, horizon_days=7)
        self.assertEqual(collision, 0.0)


# =========================================================================
# 6) COMPOSITE CPI CALCULATION ACCURACY
# =========================================================================


class CompositeCPITests(TestCase):
    """Test the Composite Pressure Index calculation."""

    def setUp(self):
        self.user = _create_test_user('cpi@example.com')
        _create_pressure_weight_config()

    def test_cpi_zero_with_empty_schedule(self):
        """No plans, no commitments → CPI = 0."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        result = compute_pressure_index(self.user, horizon_days=7)
        self.assertEqual(result['pressure_index'], 0)
        self.assertEqual(result['density_score'], 0.0)
        self.assertEqual(result['compression_score'], 0.0)

    def test_cpi_returns_all_components(self):
        """CPI result dict contains all 6 expected keys."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        result = compute_pressure_index(self.user, horizon_days=7)

        expected_keys = {
            'pressure_index', 'density_score', 'compression_score',
            'breach_risk_score', 'erosion_score', 'collision_score',
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_cpi_clamped_between_0_and_100(self):
        """CPI is always between 0 and 100."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        result = compute_pressure_index(self.user, horizon_days=7)
        self.assertGreaterEqual(result['pressure_index'], 0)
        self.assertLessEqual(result['pressure_index'], 100)

    def test_cpi_weighted_formula_accuracy(self):
        """Verify the weighted formula: CPI = sum(component × weight)."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        # Mock all components to known values
        with patch(
            'apps.core.blueprint.pressure_engine.compute_calendar_density',
            return_value=0.5,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_compression',
            return_value=0.3,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_breach_probability',
            return_value=0.4,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_goal_erosion',
            return_value=0.2,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_deadline_collisions',
            return_value=0.1,
        ):
            result = compute_pressure_index(self.user, horizon_days=7)

        # Default weights: 30/20/20/15/15
        expected = (0.5 * 30 + 0.3 * 20 + 0.4 * 20 + 0.2 * 15 + 0.1 * 15)
        # = 15 + 6 + 8 + 3 + 1.5 = 33.5 → 34
        self.assertEqual(result['pressure_index'], round(expected))

    def test_cpi_all_components_at_max(self):
        """All components at 1.0 → CPI = 100."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        with patch(
            'apps.core.blueprint.pressure_engine.compute_calendar_density',
            return_value=1.0,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_compression',
            return_value=1.0,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_breach_probability',
            return_value=1.0,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_goal_erosion',
            return_value=1.0,
        ), patch(
            'apps.core.blueprint.pressure_engine.compute_deadline_collisions',
            return_value=1.0,
        ):
            result = compute_pressure_index(self.user, horizon_days=7)

        # All weights sum to 100 → CPI = 100
        self.assertEqual(result['pressure_index'], 100)

    def test_horizon_attenuation_reduces_scores(self):
        """Longer horizons attenuate component scores."""
        from apps.core.blueprint.pressure_engine import _horizon_attenuation

        self.assertEqual(_horizon_attenuation(3), 1.0)    # Days 0-7: full
        self.assertEqual(_horizon_attenuation(7), 1.0)    # Boundary
        self.assertEqual(_horizon_attenuation(10), 0.6)   # Days 8-14: moderate
        self.assertEqual(_horizon_attenuation(14), 0.6)   # Boundary
        self.assertEqual(_horizon_attenuation(20), 0.3)   # Days 15-30: early
        self.assertEqual(_horizon_attenuation(30), 0.3)   # Boundary

    def test_pressure_snapshot_creation(self):
        """update_pressure_snapshot creates an immutable snapshot."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot
        from apps.core.blueprint.pressure_models import PressureSnapshot

        snapshot = update_pressure_snapshot(self.user, horizon_days=7)
        self.assertIsNotNone(snapshot)
        self.assertIsInstance(snapshot, PressureSnapshot)
        self.assertEqual(snapshot.user, self.user)
        self.assertEqual(snapshot.horizon_days, 7)

    def test_multiple_snapshots_are_append_only(self):
        """Each call creates a new snapshot (never overwrites)."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot
        from apps.core.blueprint.pressure_models import PressureSnapshot

        s1 = update_pressure_snapshot(self.user, horizon_days=7)
        s2 = update_pressure_snapshot(self.user, horizon_days=7)

        self.assertNotEqual(s1.pk, s2.pk)
        self.assertEqual(
            PressureSnapshot.objects.filter(user=self.user).count(), 2,
        )

    def test_pressure_weight_config_default(self):
        """Default weight config sums to 100."""
        from apps.core.blueprint.pressure_models import PressureWeightConfig

        config = PressureWeightConfig.get_active()
        total = (
            config.density_weight + config.compression_weight
            + config.breach_weight + config.erosion_weight
            + config.collision_weight
        )
        self.assertEqual(total, 100)
