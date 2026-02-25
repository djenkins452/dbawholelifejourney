"""
EAE — Model unit tests.

Tests for EAEState, EAEDecisionLog, EAEOverride, EAEEscalationEvent models
and the eae_enabled feature flag on PersonalOperatingBlueprint.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_eae.constants import (
    BUDGET_CHAT,
    CHANNEL_CHAT,
    CHANNEL_PUSH,
    COOLDOWN_AMBIGUOUS_HOURS,
    COOLDOWN_TEMPORARY_HOURS,
    ESCALATION_ACTIVE,
    ESCALATION_CRITICAL,
    ESCALATION_ELEVATED,
    ESCALATION_NOMINAL,
    ESCALATION_OVERRIDE,
    OVERRIDE_PERMANENT,
    OVERRIDE_TEMPORARY,
    PRIMARY_FOCUS_MAX_CHANGES,
    TONE_DIRECT_CLEAR,
    TONE_REFLECTIVE_GENTLE,
)
from apps.core.ai_eae.models import (
    EAEDecisionLog,
    EAEEscalationEvent,
    EAEOverride,
    EAEState,
)

User = get_user_model()


class EAEStateTests(TestCase):
    """Tests for EAEState model — per-user arbitration state."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_state@test.com",
            password="testpass123",
        )

    def test_create_default_state(self):
        """Default EAEState has nominal escalation and zero counters."""
        state = EAEState.objects.create(user=self.user)
        self.assertEqual(state.escalation_level, ESCALATION_NOMINAL)
        self.assertEqual(state.drift_risk_severity, 0.0)
        self.assertEqual(state.primary_focus_label, '')
        self.assertEqual(state.focus_changes_today, 0)
        self.assertEqual(state.noise_budget_used_today, 0)
        self.assertIsNone(state.last_arbitration_at)

    def test_one_to_one_constraint(self):
        """Only one EAEState per user."""
        EAEState.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            EAEState.objects.create(user=self.user)

    def test_reset_daily_counters_new_day(self):
        """Counters reset when date changes."""
        state = EAEState.objects.create(
            user=self.user,
            focus_changes_today=2,
            focus_date=date.today() - timedelta(days=1),
            noise_budget_used_today=5,
            noise_budget_date=date.today() - timedelta(days=1),
        )
        state.reset_daily_counters(date.today())
        self.assertEqual(state.focus_changes_today, 0)
        self.assertEqual(state.focus_date, date.today())
        self.assertEqual(state.noise_budget_used_today, 0)
        self.assertEqual(state.noise_budget_date, date.today())

    def test_reset_daily_counters_same_day(self):
        """Counters NOT reset when date hasn't changed."""
        today = date.today()
        state = EAEState.objects.create(
            user=self.user,
            focus_changes_today=1,
            focus_date=today,
            noise_budget_used_today=3,
            noise_budget_date=today,
        )
        state.reset_daily_counters(today)
        self.assertEqual(state.focus_changes_today, 1)
        self.assertEqual(state.noise_budget_used_today, 3)

    def test_focus_locked_at_max(self):
        """focus_locked returns True when max changes reached."""
        state = EAEState.objects.create(
            user=self.user,
            focus_changes_today=PRIMARY_FOCUS_MAX_CHANGES,
        )
        self.assertTrue(state.focus_locked)

    def test_focus_not_locked_below_max(self):
        """focus_locked returns False below max changes."""
        state = EAEState.objects.create(
            user=self.user,
            focus_changes_today=1,
        )
        self.assertFalse(state.focus_locked)

    def test_str_representation(self):
        """String representation includes user_id and escalation info."""
        state = EAEState.objects.create(
            user=self.user,
            escalation_level=ESCALATION_ELEVATED,
            drift_risk_severity=45.0,
        )
        s = str(state)
        self.assertIn('L1', s)
        self.assertIn('drift=45', s)

    def test_escalation_choices_valid(self):
        """All escalation levels can be set."""
        for level in [ESCALATION_NOMINAL, ESCALATION_ELEVATED,
                      ESCALATION_ACTIVE, ESCALATION_CRITICAL,
                      ESCALATION_OVERRIDE]:
            state, _ = EAEState.objects.update_or_create(
                user=self.user,
                defaults={'escalation_level': level},
            )
            self.assertEqual(state.escalation_level, level)


class EAEDecisionLogTests(TestCase):
    """Tests for EAEDecisionLog model — append-only audit."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_decision@test.com",
            password="testpass123",
        )

    def test_create_decision_log(self):
        """Create a decision log entry with all required fields."""
        log = EAEDecisionLog.objects.create(
            user=self.user,
            channel=CHANNEL_CHAT,
            escalation_level=ESCALATION_NOMINAL,
            drift_risk_severity=25.5,
            tone_band=TONE_REFLECTIVE_GENTLE,
            cognitive_units_json=[
                {'title': 'Test Unit', 'rank': 1, 'unit_type': 'single'},
            ],
            suppressed_items_json=[],
            total_candidates=5,
            surfaced_count=1,
            suppressed_count=4,
            noise_budget_used=1,
            noise_budget_max=BUDGET_CHAT,
            reason_codes=['NORMAL_OPERATION'],
            source_engines=['PIE', 'PRIE'],
            arbitration_duration_ms=12,
        )
        self.assertIsNotNone(log.decision_id)
        self.assertIsNotNone(log.created_at)
        self.assertEqual(log.channel, CHANNEL_CHAT)
        self.assertEqual(log.surfaced_count, 1)

    def test_uuid_primary_key(self):
        """Decision IDs are unique UUIDs."""
        log1 = EAEDecisionLog.objects.create(
            user=self.user,
            channel=CHANNEL_CHAT,
            escalation_level=0,
            drift_risk_severity=0,
            tone_band=TONE_REFLECTIVE_GENTLE,
        )
        log2 = EAEDecisionLog.objects.create(
            user=self.user,
            channel=CHANNEL_PUSH,
            escalation_level=0,
            drift_risk_severity=0,
            tone_band=TONE_REFLECTIVE_GENTLE,
        )
        self.assertNotEqual(log1.decision_id, log2.decision_id)

    def test_ordering_descending(self):
        """Logs ordered by most recent first."""
        EAEDecisionLog.objects.create(
            user=self.user, channel=CHANNEL_CHAT,
            escalation_level=0, drift_risk_severity=0,
            tone_band=TONE_REFLECTIVE_GENTLE,
        )
        EAEDecisionLog.objects.create(
            user=self.user, channel=CHANNEL_PUSH,
            escalation_level=0, drift_risk_severity=0,
            tone_band=TONE_REFLECTIVE_GENTLE,
        )
        logs = list(EAEDecisionLog.objects.filter(user=self.user))
        self.assertEqual(logs[0].channel, CHANNEL_PUSH)  # Most recent

    def test_str_representation(self):
        """String shows short ID, channel, level, and surfaced count."""
        log = EAEDecisionLog.objects.create(
            user=self.user, channel=CHANNEL_CHAT,
            escalation_level=ESCALATION_ACTIVE,
            drift_risk_severity=65.0,
            tone_band=TONE_DIRECT_CLEAR,
            surfaced_count=3,
        )
        s = str(log)
        self.assertIn('chat', s)
        self.assertIn('L2', s)
        self.assertIn('surfaced=3', s)

    def test_json_fields_store_complex_data(self):
        """JSON fields can store lists and dicts."""
        units = [
            {
                'unit_id': 'abc-123',
                'rank': 1,
                'title': 'Take medications',
                'source_items': [{'engine': 'PIE', 'object_id': 42}],
            },
            {
                'unit_id': 'def-456',
                'rank': 2,
                'title': 'Weight trend',
                'source_items': [{'engine': 'PRIE', 'object_id': 99}],
            },
        ]
        log = EAEDecisionLog.objects.create(
            user=self.user, channel=CHANNEL_CHAT,
            escalation_level=0, drift_risk_severity=0,
            tone_band=TONE_REFLECTIVE_GENTLE,
            cognitive_units_json=units,
            reason_codes=['NORMAL', 'BUDGET_CAP'],
            source_engines=['PIE', 'PRIE', 'PGE'],
        )
        log.refresh_from_db()
        self.assertEqual(len(log.cognitive_units_json), 2)
        self.assertEqual(log.cognitive_units_json[0]['title'], 'Take medications')
        self.assertEqual(len(log.reason_codes), 2)
        self.assertEqual(len(log.source_engines), 3)


class EAEOverrideTests(TestCase):
    """Tests for EAEOverride model — user signal suppression."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_override@test.com",
            password="testpass123",
        )

    def test_create_temporary_override(self):
        """Create a temporary override with cooldown."""
        cooldown = timezone.now() + timedelta(hours=COOLDOWN_TEMPORARY_HOURS)
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:medication_adherence',
            override_type=OVERRIDE_TEMPORARY,
            strike_count=3,
            cooldown_until=cooldown,
        )
        self.assertTrue(override.is_active)
        self.assertFalse(override.is_expired)

    def test_create_permanent_override(self):
        """Create a permanent override (no cooldown needed)."""
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:medication_adherence',
            override_type=OVERRIDE_PERMANENT,
            strike_count=3,
        )
        self.assertTrue(override.is_active)
        self.assertFalse(override.is_expired)

    def test_temporary_override_expired(self):
        """Temporary override is_expired when cooldown has passed."""
        past = timezone.now() - timedelta(hours=1)
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:weight_trend',
            override_type=OVERRIDE_TEMPORARY,
            cooldown_until=past,
        )
        self.assertFalse(override.is_active)
        self.assertTrue(override.is_expired)

    def test_permanent_override_never_expires(self):
        """Permanent overrides never expire."""
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PGE:habit_streak',
            override_type=OVERRIDE_PERMANENT,
        )
        self.assertTrue(override.is_active)
        self.assertFalse(override.is_expired)

    def test_unique_constraint(self):
        """Cannot create two overrides for same user + signal_type."""
        EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:medication_adherence',
            override_type=OVERRIDE_TEMPORARY,
        )
        with self.assertRaises(IntegrityError):
            EAEOverride.objects.create(
                user=self.user,
                signal_type='PIE:medication_adherence',
                override_type=OVERRIDE_PERMANENT,
            )

    def test_different_signal_types_allowed(self):
        """Same user can have overrides for different signal types."""
        EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:medication_adherence',
        )
        EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:weight_trend',
        )
        self.assertEqual(EAEOverride.objects.filter(user=self.user).count(), 2)

    def test_temporary_count_tracking(self):
        """temporary_count_14d tracks repeat cooldowns for auto-escalation."""
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:medication_adherence',
            override_type=OVERRIDE_TEMPORARY,
            temporary_count_14d=2,
        )
        self.assertEqual(override.temporary_count_14d, 2)

    def test_str_representation_temporary(self):
        """String shows signal type and temporary status."""
        cooldown = timezone.now() + timedelta(hours=24)
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:medication_adherence',
            override_type=OVERRIDE_TEMPORARY,
            cooldown_until=cooldown,
        )
        s = str(override)
        self.assertIn('PIE:medication_adherence', s)
        self.assertIn('temp until', s)

    def test_str_representation_permanent(self):
        """String shows permanent status."""
        override = EAEOverride.objects.create(
            user=self.user,
            signal_type='PGE:habit_streak',
            override_type=OVERRIDE_PERMANENT,
        )
        s = str(override)
        self.assertIn('permanent', s)

    def test_ambiguous_cooldown_shorter(self):
        """Ambiguous cooldown is shorter than explicit temporary."""
        self.assertLess(COOLDOWN_AMBIGUOUS_HOURS, COOLDOWN_TEMPORARY_HOURS)


class EAEEscalationEventTests(TestCase):
    """Tests for EAEEscalationEvent model — escalation transitions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_escalation@test.com",
            password="testpass123",
        )

    def test_create_escalation_event(self):
        """Create an upward escalation event."""
        event = EAEEscalationEvent.objects.create(
            user=self.user,
            direction=EAEEscalationEvent.DIRECTION_UP,
            from_level=ESCALATION_NOMINAL,
            to_level=ESCALATION_ELEVATED,
            trigger_reason="Drift score crossed 40 threshold",
            drift_risk_at_event=42.5,
        )
        self.assertIsNotNone(event.created_at)
        self.assertEqual(event.direction, 'up')
        self.assertEqual(event.from_level, 0)
        self.assertEqual(event.to_level, 1)

    def test_create_deescalation_event(self):
        """Create a downward de-escalation event."""
        event = EAEEscalationEvent.objects.create(
            user=self.user,
            direction=EAEEscalationEvent.DIRECTION_DOWN,
            from_level=ESCALATION_ELEVATED,
            to_level=ESCALATION_NOMINAL,
            trigger_reason="All de-escalation criteria met",
            drift_risk_at_event=28.0,
        )
        self.assertEqual(event.direction, 'down')
        self.assertEqual(event.from_level, 1)
        self.assertEqual(event.to_level, 0)

    def test_ordering_descending(self):
        """Events ordered most recent first."""
        EAEEscalationEvent.objects.create(
            user=self.user,
            direction=EAEEscalationEvent.DIRECTION_UP,
            from_level=0, to_level=1,
            trigger_reason="First",
            drift_risk_at_event=40.0,
        )
        EAEEscalationEvent.objects.create(
            user=self.user,
            direction=EAEEscalationEvent.DIRECTION_UP,
            from_level=1, to_level=2,
            trigger_reason="Second",
            drift_risk_at_event=60.0,
        )
        events = list(EAEEscalationEvent.objects.filter(user=self.user))
        self.assertEqual(events[0].trigger_reason, "Second")

    def test_str_up_arrow(self):
        """Upward escalation shows ↑ in string."""
        event = EAEEscalationEvent.objects.create(
            user=self.user,
            direction=EAEEscalationEvent.DIRECTION_UP,
            from_level=0, to_level=1,
            trigger_reason="Test",
            drift_risk_at_event=40.0,
        )
        self.assertIn('↑', str(event))
        self.assertIn('L0→L1', str(event))

    def test_str_down_arrow(self):
        """Downward de-escalation shows ↓ in string."""
        event = EAEEscalationEvent.objects.create(
            user=self.user,
            direction=EAEEscalationEvent.DIRECTION_DOWN,
            from_level=2, to_level=1,
            trigger_reason="Recovery",
            drift_risk_at_event=55.0,
        )
        self.assertIn('↓', str(event))
        self.assertIn('L2→L1', str(event))

    def test_multiple_events_per_user(self):
        """Multiple escalation events can exist for one user."""
        for i in range(5):
            EAEEscalationEvent.objects.create(
                user=self.user,
                direction=EAEEscalationEvent.DIRECTION_UP,
                from_level=i, to_level=min(i + 1, 4),
                trigger_reason=f"Escalation {i}",
                drift_risk_at_event=float(40 + i * 10),
            )
        self.assertEqual(
            EAEEscalationEvent.objects.filter(user=self.user).count(),
            5,
        )


class BlueprintEAEEnabledTests(TestCase):
    """Tests for eae_enabled feature flag on PersonalOperatingBlueprint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="eae_flag@test.com",
            password="testpass123",
        )

    def test_eae_disabled_by_default(self):
        """eae_enabled defaults to False."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.objects.create(user=self.user)
        self.assertFalse(bp.eae_enabled)

    def test_eae_can_be_enabled(self):
        """eae_enabled can be set to True."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.objects.create(
            user=self.user,
            eae_enabled=True,
        )
        self.assertTrue(bp.eae_enabled)

    def test_eae_toggle(self):
        """eae_enabled can be toggled."""
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        bp = PersonalOperatingBlueprint.objects.create(user=self.user)
        self.assertFalse(bp.eae_enabled)
        bp.eae_enabled = True
        bp.save()
        bp.refresh_from_db()
        self.assertTrue(bp.eae_enabled)


class ConstantsTests(TestCase):
    """Tests for EAE constants consistency and correctness."""

    def test_normalization_weights_sum_to_one(self):
        """Scoring weights must sum to 1.0."""
        from apps.core.ai_eae.constants import (
            WEIGHT_DRIFT_ANCHOR,
            WEIGHT_GOVERNANCE,
            WEIGHT_LOCAL_SCORE,
            WEIGHT_RECENCY,
        )
        total = WEIGHT_LOCAL_SCORE + WEIGHT_DRIFT_ANCHOR + WEIGHT_GOVERNANCE + WEIGHT_RECENCY
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_budget_floor_positive(self):
        """Budget floor must be at least 1."""
        from apps.core.ai_eae.constants import BUDGET_FLOOR
        self.assertGreaterEqual(BUDGET_FLOOR, 1)

    def test_channel_budgets_not_exceed_max(self):
        """Default budgets must not exceed hard maximums."""
        from apps.core.ai_eae.constants import (
            CHANNEL_BUDGET_MAP,
            CHANNEL_BUDGET_MAX_MAP,
        )
        for channel, default in CHANNEL_BUDGET_MAP.items():
            max_budget = CHANNEL_BUDGET_MAX_MAP[channel]
            self.assertLessEqual(
                default, max_budget,
                f"Default budget {default} exceeds max {max_budget} for {channel}",
            )

    def test_escalation_drift_thresholds_ascending(self):
        """Drift thresholds increase with escalation level."""
        from apps.core.ai_eae.constants import ESCALATION_DRIFT_THRESHOLDS
        thresholds = [ESCALATION_DRIFT_THRESHOLDS[i] for i in range(5)]
        for i in range(len(thresholds) - 1):
            self.assertLess(thresholds[i], thresholds[i + 1])

    def test_confidence_thresholds_ordered(self):
        """Push confidence > Chat confidence > Briefing confidence."""
        from apps.core.ai_eae.constants import (
            CONFIDENCE_MIN_BRIEFING,
            CONFIDENCE_MIN_CHAT,
            CONFIDENCE_MIN_PUSH,
        )
        self.assertGreater(CONFIDENCE_MIN_PUSH, CONFIDENCE_MIN_CHAT)
        self.assertGreater(CONFIDENCE_MIN_CHAT, CONFIDENCE_MIN_BRIEFING)

    def test_all_channels_have_budget_and_confidence(self):
        """Every channel has entries in budget, max, and confidence maps."""
        from apps.core.ai_eae.constants import (
            CHANNEL_BUDGET_MAP,
            CHANNEL_BUDGET_MAX_MAP,
            CHANNEL_CONFIDENCE_MAP,
        )
        for channel in CHANNEL_BUDGET_MAP:
            self.assertIn(channel, CHANNEL_BUDGET_MAX_MAP)
            self.assertIn(channel, CHANNEL_CONFIDENCE_MAP)

    def test_tone_map_covers_all_escalation_levels(self):
        """Every escalation level maps to a tone band."""
        from apps.core.ai_eae.constants import ESCALATION_TONE_MAP
        for level in range(5):
            self.assertIn(level, ESCALATION_TONE_MAP)
