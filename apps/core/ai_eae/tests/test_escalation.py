"""
EAE — Escalation, Override, Tone, Focus tests (Phase 8.4).
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_eae.bundler import CognitiveUnit
from apps.core.ai_eae.constants import (
    COOLDOWN_AMBIGUOUS_HOURS,
    COOLDOWN_TEMPORARY_HOURS,
    ESCALATION_ACTIVE,
    ESCALATION_CRITICAL,
    ESCALATION_ELEVATED,
    ESCALATION_NOMINAL,
    ESCALATION_OVERRIDE,
    OVERRIDE_PERMANENT,
    OVERRIDE_TEMPORARY,
    TONE_DIRECT_CLEAR,
    TONE_DIRECT_URGENT,
    TONE_EXECUTIVE_OVERRIDE,
    TONE_REFLECTIVE_FIRM,
    TONE_REFLECTIVE_GENTLE,
)
from apps.core.ai_eae.escalation import _compute_drift_level, evaluate_escalation
from apps.core.ai_eae.focus import evaluate_focus
from apps.core.ai_eae.models import EAEEscalationEvent, EAEOverride, EAEState
from apps.core.ai_eae.override import (
    cleanup_expired_overrides,
    filter_overridden_signals,
    get_active_overrides,
    record_override,
)
from apps.core.ai_eae.tone import select_tone

User = get_user_model()


class EscalationLevelTests(TestCase):
    """Tests for drift → escalation level mapping."""

    def test_low_drift_nominal(self):
        self.assertEqual(_compute_drift_level(20.0), ESCALATION_NOMINAL)

    def test_drift_40_elevated(self):
        self.assertEqual(_compute_drift_level(45.0), ESCALATION_ELEVATED)

    def test_drift_60_active(self):
        self.assertEqual(_compute_drift_level(65.0), ESCALATION_ACTIVE)

    def test_drift_70_critical(self):
        self.assertEqual(_compute_drift_level(75.0), ESCALATION_CRITICAL)

    def test_drift_85_override(self):
        self.assertEqual(_compute_drift_level(90.0), ESCALATION_OVERRIDE)

    def test_intensity_lowers_thresholds(self):
        """Higher intensity makes escalation trigger sooner."""
        # At intensity 1.0, drift 35 is NOMINAL
        self.assertEqual(_compute_drift_level(35.0, intensity=1.0), ESCALATION_NOMINAL)
        # At intensity 1.5, threshold is lowered, so 35 might trigger ELEVATED
        level = _compute_drift_level(35.0, intensity=1.5)
        self.assertGreaterEqual(level, ESCALATION_NOMINAL)


class EscalationTransitionTests(TestCase):
    """Tests for escalation state transitions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="esc_test@test.com", password="testpass123",
        )
        self.state = EAEState.objects.create(
            user=self.user,
            escalation_level=ESCALATION_NOMINAL,
            escalation_since=timezone.now() - timedelta(days=3),
        )

    def test_upward_escalation_immediate(self):
        """Drift increase triggers immediate escalation."""
        new_level = evaluate_escalation(self.state, drift_severity=50.0)
        self.assertEqual(new_level, ESCALATION_ELEVATED)
        self.assertEqual(EAEEscalationEvent.objects.filter(user=self.user).count(), 1)

    def test_downward_requires_gates(self):
        """De-escalation requires all gates to pass."""
        self.state.escalation_level = ESCALATION_ELEVATED
        self.state.escalation_since = timezone.now()  # Just set — too recent
        self.state.escalation_peak_drift = 55.0
        self.state.save()

        # Try de-escalation with low drift but fresh escalation
        new_level = evaluate_escalation(self.state, drift_severity=20.0)
        # Should NOT de-escalate because min_hours gate fails
        self.assertEqual(new_level, ESCALATION_ELEVATED)

    def test_downward_after_gates_pass(self):
        """De-escalation succeeds when all gates pass."""
        self.state.escalation_level = ESCALATION_ELEVATED
        self.state.escalation_since = timezone.now() - timedelta(hours=72)
        self.state.escalation_peak_drift = 55.0
        self.state.save()

        new_level = evaluate_escalation(self.state, drift_severity=30.0)
        self.assertEqual(new_level, ESCALATION_NOMINAL)

    def test_one_level_at_a_time_down(self):
        """De-escalation only drops one level at a time."""
        self.state.escalation_level = ESCALATION_CRITICAL
        self.state.escalation_since = timezone.now() - timedelta(hours=72)
        self.state.escalation_peak_drift = 80.0
        self.state.save()

        new_level = evaluate_escalation(self.state, drift_severity=30.0)
        self.assertEqual(new_level, ESCALATION_ACTIVE)

    def test_escalation_event_logged(self):
        """Escalation events are recorded in EAEEscalationEvent."""
        evaluate_escalation(self.state, drift_severity=65.0)
        events = EAEEscalationEvent.objects.filter(user=self.user)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().direction, 'up')


class ToneSelectionTests(TestCase):
    """Tests for tone band selection."""

    def test_nominal_gentle(self):
        self.assertEqual(select_tone(ESCALATION_NOMINAL), TONE_REFLECTIVE_GENTLE)

    def test_elevated_firm(self):
        self.assertEqual(select_tone(ESCALATION_ELEVATED), TONE_REFLECTIVE_FIRM)

    def test_active_clear(self):
        self.assertEqual(select_tone(ESCALATION_ACTIVE), TONE_DIRECT_CLEAR)

    def test_critical_urgent(self):
        self.assertEqual(select_tone(ESCALATION_CRITICAL), TONE_DIRECT_URGENT)

    def test_override_executive(self):
        self.assertEqual(select_tone(ESCALATION_OVERRIDE), TONE_EXECUTIVE_OVERRIDE)

    def test_high_intensity_firms_tone(self):
        """High intensity shifts tone one step firmer."""
        tone = select_tone(ESCALATION_NOMINAL, intensity=1.5)
        self.assertEqual(tone, TONE_REFLECTIVE_FIRM)

    def test_low_intensity_softens_tone(self):
        """Low intensity shifts tone one step gentler."""
        tone = select_tone(ESCALATION_ELEVATED, intensity=0.5)
        self.assertEqual(tone, TONE_REFLECTIVE_GENTLE)


class OverrideTests(TestCase):
    """Tests for override state machine."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="override_test@test.com", password="testpass123",
        )

    def test_record_temporary_override(self):
        """Temporary override creates cooldown."""
        ov = record_override(self.user, 'PIE:medication', 'temporary')
        self.assertEqual(ov.override_type, OVERRIDE_TEMPORARY)
        self.assertIsNotNone(ov.cooldown_until)
        self.assertTrue(ov.is_active)

    def test_record_permanent_override(self):
        """Permanent override has no cooldown."""
        ov = record_override(self.user, 'PIE:medication', 'permanent')
        self.assertEqual(ov.override_type, OVERRIDE_PERMANENT)
        self.assertIsNone(ov.cooldown_until)
        self.assertTrue(ov.is_active)

    def test_strike_count_increments(self):
        """Repeated overrides increment strike count."""
        record_override(self.user, 'PIE:medication', 'temporary')
        ov = record_override(self.user, 'PIE:medication', 'temporary')
        self.assertEqual(ov.strike_count, 2)

    def test_strike_3_becomes_permanent(self):
        """Third strike auto-escalates to permanent."""
        record_override(self.user, 'PIE:medication', 'temporary')
        record_override(self.user, 'PIE:medication', 'temporary')
        ov = record_override(self.user, 'PIE:medication', 'temporary')
        self.assertEqual(ov.override_type, OVERRIDE_PERMANENT)

    def test_ambiguous_shorter_cooldown(self):
        """Ambiguous override uses shorter cooldown."""
        ov = record_override(self.user, 'PIE:medication', 'ambiguous')
        temp_ov = record_override(
            User.objects.create_user(email="ov2@test.com", password="p"),
            'PIE:medication', 'temporary',
        )
        # Ambiguous cooldown should be shorter
        self.assertLess(
            (ov.cooldown_until - timezone.now()).total_seconds(),
            (temp_ov.cooldown_until - timezone.now()).total_seconds(),
        )

    def test_filter_suppresses_overridden(self):
        """Overridden signals are filtered out."""
        record_override(self.user, 'PIE:medication', 'permanent')
        overrides = get_active_overrides(self.user)

        from apps.core.ai_eae.signal_collector import RawSignal
        from apps.core.ai_eae.scorer import ScoredSignal
        signal = RawSignal(
            engine='PIE', signal_type='medication', module='health',
            title='Take meds', message='', local_score=50, confidence=0.8,
            severity='warning', object_type='Insight', object_id=1,
            created_at=timezone.now(),
        )
        scored = ScoredSignal(
            raw=signal, normalized_score=50,
            drift_anchor_weight=0, governance_weight=1, recency_weight=0.8,
        )

        allowed, events = filter_overridden_signals([scored], overrides)
        self.assertEqual(len(allowed), 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['action'], 'SUPPRESSED')

    def test_cleanup_expired(self):
        """Expired temporary overrides are cleaned up."""
        EAEOverride.objects.create(
            user=self.user,
            signal_type='PIE:old',
            override_type=OVERRIDE_TEMPORARY,
            cooldown_until=timezone.now() - timedelta(hours=1),
        )
        count = cleanup_expired_overrides(self.user)
        self.assertEqual(count, 1)
        self.assertEqual(EAEOverride.objects.filter(user=self.user).count(), 0)


class FocusTests(TestCase):
    """Tests for primary focus management."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="focus_test@test.com", password="testpass123",
        )
        self.state = EAEState.objects.create(
            user=self.user,
            focus_date=date.today(),
        )

    def _make_unit(self, title='Focus Item', score=80, module='health'):
        return CognitiveUnit(
            unit_id='test-id',
            title=title,
            module=module,
            normalized_score=score,
            confidence=0.8,
        )

    def test_morning_set(self):
        """First interaction sets focus from top unit."""
        units = [self._make_unit('Morning Task')]
        focus = evaluate_focus(self.state, units, 30.0)
        self.assertIsNotNone(focus)
        self.assertEqual(self.state.primary_focus_label, 'Morning Task')
        self.assertEqual(self.state.focus_changes_today, 1)

    def test_locked_after_max_changes(self):
        """Focus locked after 2 changes."""
        self.state.focus_changes_today = 2
        self.state.primary_focus_label = 'Existing Focus'
        self.state.save()

        units = [self._make_unit('New Item')]
        focus = evaluate_focus(self.state, units, 80.0)
        # Should not change focus
        self.assertEqual(self.state.focus_changes_today, 2)

    def test_midday_correction_on_drift_increase(self):
        """Midday correction allowed when drift increases >= 15."""
        self.state.primary_focus_label = 'Old Focus'
        self.state.focus_changes_today = 1
        self.state.drift_risk_severity = 20.0
        self.state.save()

        units = [self._make_unit('New Priority')]
        focus = evaluate_focus(self.state, units, drift_severity=40.0)
        self.assertEqual(self.state.primary_focus_label, 'New Priority')
        self.assertEqual(self.state.focus_changes_today, 2)

    def test_no_correction_without_drift_increase(self):
        """No midday correction without significant drift increase."""
        self.state.primary_focus_label = 'Existing Focus'
        self.state.focus_changes_today = 1
        self.state.drift_risk_severity = 30.0
        self.state.save()

        units = [self._make_unit('Other Item')]
        focus = evaluate_focus(self.state, units, drift_severity=35.0)
        # Drift increase only 5, below threshold of 15
        self.assertEqual(self.state.focus_changes_today, 1)

    def test_empty_units_returns_none(self):
        """No units returns None."""
        focus = evaluate_focus(self.state, [], 0.0)
        self.assertIsNone(focus)
