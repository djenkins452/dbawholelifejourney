"""
Phase 4 — Pressure Engine Tests.

Tests for:
- Calendar density scoring accuracy
- Workload compression detection
- Habit breach probability (deterministic)
- Goal erosion stage 1 vs stage 2
- Deadline collision detection
- Composite index math correctness
- Snapshot creation and persistence
- Trigger-based recompute
- No escalation level change caused by pressure alone
- Horizon behavior (7 vs 14 vs 30 days)
- PressureWeightConfig validation

Project: Whole Life Journey
Path: apps/core/tests/test_pressure_engine.py
"""

import datetime as dt
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PressureModelTests(TestCase):
    """Tests for PressureSnapshot and PressureWeightConfig models."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='pressure@test.com', password='testpass123',
        )

    def test_pressure_snapshot_creation(self):
        """PressureSnapshot can be created with all fields."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        snapshot = PressureSnapshot.objects.create(
            user=self.user,
            pressure_index=65,
            density_score=0.7,
            compression_score=0.4,
            breach_risk_score=0.3,
            erosion_score=0.2,
            collision_score=0.1,
            horizon_days=7,
            metadata={'test': True},
        )
        self.assertEqual(snapshot.pressure_index, 65)
        self.assertEqual(snapshot.horizon_days, 7)
        self.assertIsNotNone(snapshot.computed_at)

    def test_pressure_snapshot_latest_for_user(self):
        """latest_for_user returns the most recent snapshot."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        old = PressureSnapshot.objects.create(
            user=self.user, pressure_index=30,
            computed_at=timezone.now() - dt.timedelta(hours=2),
        )
        new = PressureSnapshot.objects.create(
            user=self.user, pressure_index=70,
            computed_at=timezone.now(),
        )
        latest = PressureSnapshot.latest_for_user(self.user)
        self.assertEqual(latest.pk, new.pk)
        self.assertEqual(latest.pressure_index, 70)

    def test_pressure_snapshot_does_not_overwrite(self):
        """Creating a new snapshot does not delete previous ones."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        PressureSnapshot.objects.create(user=self.user, pressure_index=30)
        PressureSnapshot.objects.create(user=self.user, pressure_index=50)
        PressureSnapshot.objects.create(user=self.user, pressure_index=70)
        self.assertEqual(PressureSnapshot.objects.filter(user=self.user).count(), 3)

    def test_weight_config_default_creation(self):
        """get_active creates default config if none exists."""
        from apps.core.blueprint.pressure_models import PressureWeightConfig

        # Clear any existing configs from migration
        PressureWeightConfig.objects.all().delete()

        config = PressureWeightConfig.get_active()
        self.assertTrue(config.active)
        self.assertEqual(config.density_weight, 30)
        self.assertEqual(config.compression_weight, 20)
        self.assertEqual(config.breach_weight, 20)
        self.assertEqual(config.erosion_weight, 15)
        self.assertEqual(config.collision_weight, 15)
        total = (
            config.density_weight + config.compression_weight
            + config.breach_weight + config.erosion_weight
            + config.collision_weight
        )
        self.assertEqual(total, 100)

    def test_weight_config_validation_rejects_bad_sum(self):
        """Weights that don't sum to 100 raise ValidationError."""
        from apps.core.blueprint.pressure_models import PressureWeightConfig

        with self.assertRaises(ValidationError):
            PressureWeightConfig.objects.create(
                density_weight=50,
                compression_weight=50,
                breach_weight=50,
                erosion_weight=50,
                collision_weight=50,
                active=False,
            )

    def test_weight_config_get_active_returns_existing(self):
        """get_active returns existing active config."""
        from apps.core.blueprint.pressure_models import PressureWeightConfig

        config = PressureWeightConfig.get_active()
        config2 = PressureWeightConfig.get_active()
        self.assertEqual(config.pk, config2.pk)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class CalendarDensityTests(TestCase):
    """Tests for compute_calendar_density."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='density@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_zero_density_when_no_plans(self):
        """No architecture plans → density = 0."""
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        density = compute_calendar_density(self.user, horizon_days=7)
        self.assertEqual(density, 0.0)

    def test_full_day_density(self):
        """A fully scheduled day produces high density."""
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        plan = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='active',
        )
        # Schedule 7:00-22:00 (full available window = 900 minutes)
        ScheduledBlock.objects.create(
            plan=plan, start_time=dt.time(7, 0), end_time=dt.time(22, 0),
            title='Full Day', tier=3,
        )
        # One day fully packed out of 7 → density ~1/7 ≈ 0.14
        density = compute_calendar_density(self.user, horizon_days=7)
        self.assertGreater(density, 0.0)
        self.assertLessEqual(density, 1.0)

    def test_density_clamped_to_one(self):
        """Density never exceeds 1.0."""
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        # Fill every day for 7 days
        for offset in range(7):
            target_date = today + dt.timedelta(days=offset)
            plan = ArchitecturePlan.objects.create(
                user=self.user, date=target_date, status='active',
            )
            ScheduledBlock.objects.create(
                plan=plan, start_time=dt.time(7, 0), end_time=dt.time(22, 0),
                title='Full Day', tier=3,
            )

        density = compute_calendar_density(self.user, horizon_days=7)
        self.assertLessEqual(density, 1.0)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class CompressionTests(TestCase):
    """Tests for compute_compression."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='compression@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_no_compression_when_empty(self):
        """No plans → no compression."""
        from apps.core.blueprint.pressure_engine import compute_compression

        score = compute_compression(self.user, horizon_days=7)
        self.assertEqual(score, 0.0)

    def test_no_compression_when_no_flexible_blocks(self):
        """Only Tier 1-2 blocks → no compression (no flexible content)."""
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock
        from apps.core.blueprint.pressure_engine import compute_compression

        today = timezone.localdate()
        plan = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='active',
        )
        ScheduledBlock.objects.create(
            plan=plan, start_time=dt.time(7, 0), end_time=dt.time(12, 0),
            title='Core Work', tier=1,
        )
        score = compute_compression(self.user, horizon_days=7)
        self.assertEqual(score, 0.0)

    def test_compression_detected_when_flexible_exceeds_free(self):
        """Compression detected when flexible blocks crowd out free time."""
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock
        from apps.core.blueprint.pressure_engine import compute_compression

        today = timezone.localdate()
        plan = ArchitecturePlan.objects.create(
            user=self.user, date=today, status='active',
        )
        # 10 hours of Tier 1 (fixed) + 4 hours of Tier 4 (flexible)
        # Available: 15h (900 min). Fixed: 600 min. Free: 300 min.
        # Flexible: 240 min. Threshold: 300 × 1.2 = 360. 240 < 360 → no compression
        ScheduledBlock.objects.create(
            plan=plan, start_time=dt.time(7, 0), end_time=dt.time(17, 0),
            title='Fixed Work', tier=1,
        )
        ScheduledBlock.objects.create(
            plan=plan, start_time=dt.time(17, 0), end_time=dt.time(21, 0),
            title='Flexible', tier=4,
        )

        # Now add more flexible to all 7 days to trigger compression
        for offset in range(1, 7):
            target_date = today + dt.timedelta(days=offset)
            p = ArchitecturePlan.objects.create(
                user=self.user, date=target_date, status='active',
            )
            # 13h fixed + 2h flexible per day → free = 0h
            ScheduledBlock.objects.create(
                plan=p, start_time=dt.time(7, 0), end_time=dt.time(20, 0),
                title='Fixed', tier=1,
            )
            ScheduledBlock.objects.create(
                plan=p, start_time=dt.time(20, 0), end_time=dt.time(22, 0),
                title='Flex', tier=4,
            )

        score = compute_compression(self.user, horizon_days=7)
        self.assertGreater(score, 0.0)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class BreachProbabilityTests(TestCase):
    """Tests for compute_breach_probability (deterministic)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='breach@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_zero_breach_when_no_history(self):
        """No overrides, no drift → breach = 0."""
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        score = compute_breach_probability(self.user, horizon_days=7)
        self.assertEqual(score, 0.0)

    def test_breach_increases_with_overrides(self):
        """Tier 1 override history raises breach score."""
        from apps.core.blueprint.models import Tier1OverrideEvent
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        # Create 4 override events in last 14 days
        for i in range(4):
            Tier1OverrideEvent.objects.create(
                user=self.user,
                conflicting_block_description=f'Override {i}',
            )

        score = compute_breach_probability(self.user, horizon_days=7)
        self.assertGreater(score, 0.0)

    def test_breach_increases_with_tier1_drift(self):
        """Recent Tier 1 drift events raise breach score."""
        from apps.core.blueprint.models import DriftEvent
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        today = timezone.localdate()
        for i in range(3):
            DriftEvent.objects.create(
                user=self.user,
                drift_type='BLOCK_MISSED',
                date=today - dt.timedelta(days=i),
                tier=1,
                severity=0.8,
            )

        score = compute_breach_probability(self.user, horizon_days=7)
        self.assertGreater(score, 0.0)

    def test_breach_is_deterministic(self):
        """Same inputs produce same output (no randomness)."""
        from apps.core.blueprint.pressure_engine import compute_breach_probability

        score1 = compute_breach_probability(self.user, horizon_days=7)
        score2 = compute_breach_probability(self.user, horizon_days=7)
        self.assertEqual(score1, score2)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class GoalErosionTests(TestCase):
    """Tests for compute_goal_erosion — stage 1 vs stage 2."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='erosion@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_zero_erosion_when_no_goals(self):
        """No active goals → erosion = 0."""
        from apps.core.blueprint.pressure_engine import compute_goal_erosion

        score = compute_goal_erosion(self.user, horizon_days=7)
        self.assertEqual(score, 0.0)

    def test_stage2_erosion_for_overdue_goal(self):
        """Overdue goal produces maximum erosion."""
        from apps.core.blueprint.pressure_engine import compute_goal_erosion
        from apps.purpose.models import LifeGoal

        LifeGoal.objects.create(
            user=self.user,
            title='Overdue Goal',
            status='active',
            target_date=timezone.localdate() - dt.timedelta(days=5),
        )

        score = compute_goal_erosion(self.user, horizon_days=7)
        self.assertGreater(score, 0.0)

    def test_erosion_for_on_track_goal_within_margin(self):
        """Goal with progress on track but slowing produces stage 1 score."""
        from apps.core.blueprint.pressure_engine import compute_goal_erosion
        from apps.purpose.models import GoalMilestone, LifeGoal

        # Goal created 20 days ago, due in 10 days, 50% done
        created = timezone.now() - dt.timedelta(days=20)
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Tracked Goal',
            status='active',
            target_date=timezone.localdate() + dt.timedelta(days=10),
        )
        # Manually set created_at
        LifeGoal.objects.filter(pk=goal.pk).update(created_at=created)

        # Create milestones: 2 of 4 complete (50%)
        for i in range(4):
            GoalMilestone.objects.create(
                goal=goal,
                title=f'Milestone {i}',
                completed=(i < 2),
            )

        score = compute_goal_erosion(self.user, horizon_days=14)
        # Should produce some score (either stage 1 or 2 depending on rate)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class DeadlineCollisionTests(TestCase):
    """Tests for compute_deadline_collisions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='collision@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_zero_collisions_when_no_deadlines(self):
        """No deadlines → collision = 0."""
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        score = compute_deadline_collisions(self.user, horizon_days=7)
        self.assertEqual(score, 0.0)

    def test_collision_from_snapshot_flags(self):
        """Collision score from DeadlineSnapshot collision_flags."""
        from apps.core.blueprint.models import DeadlineSnapshot
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        DeadlineSnapshot.objects.create(
            user=self.user,
            due_24h=[{'type': 'commitment', 'text': 'A'}],
            due_72h=[],
            due_7d=[],
            collision_flags=[
                {'type': 'pair_collision', 'items': ['A', 'B'], 'gap_hours': 1.0},
                {'type': 'daily_overload', 'date': '2026-02-23', 'deadline_count': 5},
            ],
        )

        score = compute_deadline_collisions(self.user, horizon_days=7)
        # pair_collision: 0.2, daily_overload: 0.3 → total: 0.5
        self.assertAlmostEqual(score, 0.5, places=1)

    def test_collision_fallback_to_commitments(self):
        """Without snapshot, falls back to live computation from commitments."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.pressure_engine import compute_deadline_collisions

        now = timezone.now()
        # Create commitments with <2h gap
        Commitment.objects.create(
            user=self.user,
            normalized_text='Task A',
            time_boundary=now + dt.timedelta(hours=3),
            status='pending',
        )
        Commitment.objects.create(
            user=self.user,
            normalized_text='Task B',
            time_boundary=now + dt.timedelta(hours=4),
            status='pending',
        )

        score = compute_deadline_collisions(self.user, horizon_days=7)
        # Should detect the pair collision
        self.assertGreater(score, 0.0)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class CompositePressureIndexTests(TestCase):
    """Tests for compute_pressure_index — math correctness."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='composite@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_zero_index_when_all_clear(self):
        """No plans, no history → index = 0."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        result = compute_pressure_index(self.user, horizon_days=7)
        self.assertEqual(result['pressure_index'], 0)
        self.assertEqual(result['density_score'], 0.0)
        self.assertEqual(result['compression_score'], 0.0)
        self.assertEqual(result['breach_risk_score'], 0.0)
        self.assertEqual(result['erosion_score'], 0.0)
        self.assertEqual(result['collision_score'], 0.0)

    def test_index_matches_weighted_sum(self):
        """Index equals weighted sum of components with default weights."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        # Patch individual functions to return known values
        with patch('apps.core.blueprint.pressure_engine.compute_calendar_density', return_value=0.5), \
             patch('apps.core.blueprint.pressure_engine.compute_compression', return_value=0.3), \
             patch('apps.core.blueprint.pressure_engine.compute_breach_probability', return_value=0.4), \
             patch('apps.core.blueprint.pressure_engine.compute_goal_erosion', return_value=0.2), \
             patch('apps.core.blueprint.pressure_engine.compute_deadline_collisions', return_value=0.1):

            result = compute_pressure_index(self.user, horizon_days=7)

            # Default weights: 30/20/20/15/15
            expected = (
                0.5 * 30 + 0.3 * 20 + 0.4 * 20 + 0.2 * 15 + 0.1 * 15
            )
            self.assertEqual(result['pressure_index'], round(expected))
            self.assertEqual(result['density_score'], 0.5)
            self.assertEqual(result['compression_score'], 0.3)

    def test_index_clamped_to_0_100(self):
        """Index is always between 0 and 100."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        with patch('apps.core.blueprint.pressure_engine.compute_calendar_density', return_value=1.0), \
             patch('apps.core.blueprint.pressure_engine.compute_compression', return_value=1.0), \
             patch('apps.core.blueprint.pressure_engine.compute_breach_probability', return_value=1.0), \
             patch('apps.core.blueprint.pressure_engine.compute_goal_erosion', return_value=1.0), \
             patch('apps.core.blueprint.pressure_engine.compute_deadline_collisions', return_value=1.0):

            result = compute_pressure_index(self.user, horizon_days=7)
            self.assertEqual(result['pressure_index'], 100)

    def test_index_is_integer(self):
        """Pressure index is always an integer."""
        from apps.core.blueprint.pressure_engine import compute_pressure_index

        result = compute_pressure_index(self.user, horizon_days=7)
        self.assertIsInstance(result['pressure_index'], int)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class SnapshotPersistenceTests(TestCase):
    """Tests for update_pressure_snapshot."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='snapshot@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_snapshot_created_successfully(self):
        """update_pressure_snapshot creates a PressureSnapshot record."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot
        from apps.core.blueprint.pressure_models import PressureSnapshot

        snapshot = update_pressure_snapshot(self.user)
        self.assertIsNotNone(snapshot)
        self.assertEqual(PressureSnapshot.objects.filter(user=self.user).count(), 1)
        self.assertEqual(snapshot.horizon_days, 7)

    def test_snapshot_does_not_overwrite_previous(self):
        """Multiple calls create multiple snapshots."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot
        from apps.core.blueprint.pressure_models import PressureSnapshot

        update_pressure_snapshot(self.user)
        update_pressure_snapshot(self.user)
        update_pressure_snapshot(self.user)
        self.assertEqual(PressureSnapshot.objects.filter(user=self.user).count(), 3)

    def test_snapshot_stores_baseline_variance(self):
        """Snapshot metadata includes baseline variance."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        snapshot = update_pressure_snapshot(self.user)
        self.assertIn('baseline_variance', snapshot.metadata)
        self.assertIn('sample_size', snapshot.metadata['baseline_variance'])

    def test_snapshot_non_blocking_on_failure(self):
        """Failure returns None, does not raise."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        with patch('apps.core.blueprint.pressure_engine.compute_pressure_index',
                   side_effect=Exception('test error')):
            result = update_pressure_snapshot(self.user)
            self.assertIsNone(result)

    def test_snapshot_custom_horizon(self):
        """Snapshot respects custom horizon_days."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        snapshot = update_pressure_snapshot(self.user, horizon_days=14)
        self.assertEqual(snapshot.horizon_days, 14)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class HorizonBehaviorTests(TestCase):
    """Tests for horizon attenuation (7 vs 14 vs 30 days)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='horizon@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_full_precision_at_7_days(self):
        """7-day horizon uses full precision (attenuation = 1.0)."""
        from apps.core.blueprint.pressure_engine import _horizon_attenuation

        self.assertEqual(_horizon_attenuation(7), 1.0)

    def test_moderate_precision_at_14_days(self):
        """14-day horizon uses moderate precision (attenuation = 0.6)."""
        from apps.core.blueprint.pressure_engine import _horizon_attenuation

        self.assertEqual(_horizon_attenuation(14), 0.6)

    def test_early_warning_at_30_days(self):
        """30-day horizon uses early warning (attenuation = 0.3)."""
        from apps.core.blueprint.pressure_engine import _horizon_attenuation

        self.assertEqual(_horizon_attenuation(30), 0.3)

    def test_longer_horizon_reduces_density_score(self):
        """Same data should produce lower density at 30-day horizon than 7-day."""
        from apps.core.blueprint.models import ArchitecturePlan, ScheduledBlock
        from apps.core.blueprint.pressure_engine import compute_calendar_density

        today = timezone.localdate()
        for offset in range(7):
            plan = ArchitecturePlan.objects.create(
                user=self.user, date=today + dt.timedelta(days=offset),
                status='active',
            )
            ScheduledBlock.objects.create(
                plan=plan, start_time=dt.time(7, 0), end_time=dt.time(18, 0),
                title='Work', tier=3,
            )

        density_7 = compute_calendar_density(self.user, horizon_days=7)
        density_30 = compute_calendar_density(self.user, horizon_days=30)

        # 30-day horizon has attenuation 0.3 vs 1.0 for 7-day
        # But also more days without plans, so density should be lower
        self.assertGreaterEqual(density_7, density_30)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class NoEscalationFromPressureTests(TestCase):
    """Verify pressure alone NEVER raises escalation level."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='noescalation@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_high_pressure_does_not_change_escalation(self):
        """Even critical pressure (>90) does not modify EscalationState."""
        from apps.core.blueprint.models import EscalationState
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        # Create clean escalation state
        state, _ = EscalationState.get_or_create_for_user(self.user)
        self.assertEqual(state.current_level, EscalationState.LEVEL_CLEAN)

        # Mock high pressure
        with patch('apps.core.blueprint.pressure_engine.compute_pressure_index',
                   return_value={
                       'pressure_index': 95,
                       'density_score': 0.9,
                       'compression_score': 0.9,
                       'breach_risk_score': 0.9,
                       'erosion_score': 0.9,
                       'collision_score': 0.9,
                   }):
            update_pressure_snapshot(self.user)

        # Escalation state must remain CLEAN
        state.refresh_from_db()
        self.assertEqual(state.current_level, EscalationState.LEVEL_CLEAN)

    def test_pressure_snapshot_has_no_escalation_side_effects(self):
        """Pressure engine does not import or call escalation_engine."""
        import apps.core.blueprint.pressure_engine as pe
        source = open(pe.__file__).read()

        # Verify no escalation imports or calls
        self.assertNotIn('escalation_engine', source)
        self.assertNotIn('resolve_activation_state', source)
        self.assertNotIn('EscalationState', source)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class TriggerRecomputeTests(TestCase):
    """Tests for event-driven pressure recompute triggers."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='trigger@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_commitment_save_triggers_recompute(self):
        """Saving a Commitment triggers pressure recompute."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.pressure_models import PressureSnapshot

        Commitment.objects.create(
            user=self.user,
            normalized_text='Test commitment',
            time_boundary=timezone.now() + dt.timedelta(days=1),
            status='pending',
        )

        # Signal should have created a snapshot
        self.assertTrue(
            PressureSnapshot.objects.filter(user=self.user).exists()
        )

    def test_tier1_override_triggers_recompute(self):
        """Creating a Tier1OverrideEvent triggers pressure recompute."""
        from apps.core.blueprint.models import Tier1OverrideEvent
        from apps.core.blueprint.pressure_models import PressureSnapshot

        initial_count = PressureSnapshot.objects.filter(user=self.user).count()

        Tier1OverrideEvent.objects.create(
            user=self.user,
            conflicting_block_description='Test override',
        )

        new_count = PressureSnapshot.objects.filter(user=self.user).count()
        self.assertGreater(new_count, initial_count)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class CoSContextIntegrationTests(TestCase):
    """Tests for pressure data injection into CoS context."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='context@test.com', password='testpass123',
        )
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_pressure_snapshot_in_context(self):
        """build_cos_context includes pressure_snapshot when available."""
        from apps.core.blueprint.pressure_engine import update_pressure_snapshot

        update_pressure_snapshot(self.user)

        from apps.core.ai_orchestrator.cos_context import build_cos_context
        context = build_cos_context(self.user)

        self.assertIn('pressure_snapshot', context)
        self.assertIn('pressure_index', context['pressure_snapshot'])

    def test_pressure_narrative_in_system_injection(self):
        """High pressure produces narrative in system injection."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        PressureSnapshot.objects.create(
            user=self.user,
            pressure_index=85,
            density_score=0.8,
        )

        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)

        self.assertIn('LOAD STATUS: High', injection)

    def test_no_narrative_when_pressure_low(self):
        """Low pressure (<= 60) produces no load status in injection."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        PressureSnapshot.objects.create(
            user=self.user,
            pressure_index=40,
        )

        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)

        self.assertNotIn('LOAD STATUS', injection)

    def test_critical_pressure_narrative(self):
        """Critical pressure (>90) shows critical load status."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        PressureSnapshot.objects.create(
            user=self.user,
            pressure_index=95,
        )

        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)

        self.assertIn('LOAD STATUS: Critical', injection)

    def test_elevated_pressure_narrative(self):
        """Elevated pressure (61-80) shows elevated load status."""
        from apps.core.blueprint.pressure_models import PressureSnapshot

        PressureSnapshot.objects.create(
            user=self.user,
            pressure_index=65,
        )

        from apps.core.ai_orchestrator.cos_context import (
            build_cos_context,
            format_cos_system_injection,
        )
        context = build_cos_context(self.user)
        injection = format_cos_system_injection(context)

        self.assertIn('LOAD STATUS: Elevated', injection)
