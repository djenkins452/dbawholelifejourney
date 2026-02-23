"""
Phase 5 — Protective Action Engine Tests.

Tests for:
- Recommendation generation (all 4 types)
- Alert scheduling (24h/4h/1h)
- Alert cancellation on renegotiation
- Throttle suppression
- InterventionLog overload triggers
- Escalation state NOT altered by pressure
- Human language compliance (no jargon)
- Supersede/expire behavior
- CoS context injection
- Protective briefing

Project: Whole Life Journey
Path: apps/core/tests/test_protective_engine.py
"""

import datetime as dt
import re
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User


# Tokens that must NEVER appear in user-facing message fields
FORBIDDEN_TOKENS = [
    'CPI', 'density', 'probability', '0.', 'fold=', 'zoneinfo',
    'breach_risk', 'compression_score', 'erosion_score', 'collision_score',
    'pressure_index',
]

FORBIDDEN_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(t) for t in FORBIDDEN_TOKENS) + r')\b',
    re.IGNORECASE,
)


def _create_test_user(email='protective@test.com'):
    """Create a test user with required preferences."""
    user = User.objects.create_user(email=email, password='testpass123')
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.ai_enabled = True
    prefs.personal_assistant_enabled = True
    prefs.save()
    return user


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class ProtectiveModelTests(TestCase):
    """Tests for ProtectiveRecommendation, ProtectiveAlert, ProtectiveActionLog models."""

    def setUp(self):
        self.user = _create_test_user()

    def test_recommendation_creation(self):
        """ProtectiveRecommendation can be created with all fields."""
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        rec = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
            title='Block time for what matters most',
            message='Your schedule is busier than usual.',
            call_to_action={'A': {'text': 'Suggest times', 'action_key': 'suggest'}},
            priority=70,
            related_object_type='Commitment',
            related_object_id=1,
            metadata={'cpi': 65},
        )
        self.assertEqual(rec.status, ProtectiveRecommendation.STATUS_ACTIVE)
        self.assertEqual(rec.recommendation_type, ProtectiveRecommendation.TYPE_TIME_BLOCK)
        self.assertIsNotNone(rec.created_at)

    def test_recommendation_active_for_user(self):
        """active_for_user returns only active recommendations sorted by priority."""
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        r1 = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title='Low priority', message='Test', priority=30,
        )
        r2 = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_FOCUS_PLAN,
            title='High priority', message='Test', priority=80,
        )
        ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
            title='Dismissed', message='Test', priority=90,
            status=ProtectiveRecommendation.STATUS_DISMISSED,
        )

        active = list(ProtectiveRecommendation.active_for_user(self.user))
        self.assertEqual(len(active), 2)
        self.assertEqual(active[0].pk, r2.pk)  # Higher priority first

    def test_alert_creation(self):
        """ProtectiveAlert can be created and queried."""
        from apps.core.blueprint.protective_models import ProtectiveAlert

        alert = ProtectiveAlert.objects.create(
            user=self.user,
            alert_type=ProtectiveAlert.TYPE_DEADLINE_24H,
            message='Reminder: Your commitment is due tomorrow.',
            scheduled_for=timezone.now() + dt.timedelta(hours=23),
            related_object_type='Commitment',
            related_object_id=1,
        )
        self.assertEqual(alert.delivery_status, ProtectiveAlert.DELIVERY_PENDING)

    def test_alert_pending_due(self):
        """pending_due returns only due pending alerts."""
        from apps.core.blueprint.protective_models import ProtectiveAlert

        now = timezone.now()
        due = ProtectiveAlert.objects.create(
            user=self.user,
            alert_type=ProtectiveAlert.TYPE_DEADLINE_4H,
            message='Due alert', scheduled_for=now - dt.timedelta(minutes=5),
        )
        future = ProtectiveAlert.objects.create(
            user=self.user,
            alert_type=ProtectiveAlert.TYPE_DEADLINE_1H,
            message='Future alert', scheduled_for=now + dt.timedelta(hours=2),
        )
        delivered = ProtectiveAlert.objects.create(
            user=self.user,
            alert_type=ProtectiveAlert.TYPE_DEADLINE_24H,
            message='Already delivered', scheduled_for=now - dt.timedelta(hours=1),
            delivery_status=ProtectiveAlert.DELIVERY_DELIVERED,
        )

        pending = list(ProtectiveAlert.pending_due(now))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].pk, due.pk)

    def test_action_log_creation(self):
        """ProtectiveActionLog can be created."""
        from apps.core.blueprint.protective_models import ProtectiveActionLog

        log = ProtectiveActionLog.objects.create(
            user=self.user,
            event_type=ProtectiveActionLog.EVENT_CREATED_RECOMMENDATION,
            object_type='ProtectiveRecommendation',
            object_id=1,
            rationale='Test log entry',
        )
        self.assertIsNotNone(log.timestamp)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class RecommendationGenerationTests(TestCase):
    """Tests for compute_protective_recommendations."""

    def setUp(self):
        self.user = _create_test_user('recs@test.com')
        self.now = timezone.now()

    def _create_pressure_snapshot(self, cpi=65, breach=0.3, density=0.5):
        """Create a PressureSnapshot without triggering signals."""
        from apps.core.blueprint.pressure_models import PressureSnapshot
        snapshot = PressureSnapshot(
            user=self.user,
            pressure_index=cpi,
            density_score=density,
            compression_score=0.3,
            breach_risk_score=breach,
            erosion_score=0.2,
            collision_score=0.1,
        )
        PressureSnapshot.objects.bulk_create([snapshot])
        return PressureSnapshot.objects.filter(user=self.user).order_by('-computed_at').first()

    @patch('apps.core.blueprint.protective_engine._has_free_gap', return_value=True)
    @patch('apps.core.blueprint.protective_engine._find_highest_risk_item')
    def test_time_block_suggestion_when_cpi_above_60(self, mock_risk, mock_gap):
        """CPI > 60 + gap exists => TIME_BLOCK_SUGGESTION."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=65)
        mock_risk.return_value = {
            'label': 'Finish report',
            'object_type': 'Commitment',
            'object_id': 1,
        }

        recs = compute_protective_recommendations(self.user, self.now)

        time_blocks = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_TIME_BLOCK]
        self.assertGreaterEqual(len(time_blocks), 1)
        self.assertIn('Finish report', time_blocks[0].message)

    @patch('apps.core.blueprint.protective_engine._has_free_gap', return_value=False)
    @patch('apps.core.blueprint.protective_engine._find_highest_risk_item')
    def test_no_time_block_when_no_gap(self, mock_risk, mock_gap):
        """CPI > 60 but no gap => no TIME_BLOCK_SUGGESTION."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=65)
        mock_risk.return_value = {'label': 'Test', 'object_type': 'Commitment', 'object_id': 1}

        recs = compute_protective_recommendations(self.user, self.now)
        time_blocks = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_TIME_BLOCK]
        self.assertEqual(len(time_blocks), 0)

    def test_no_recommendations_when_cpi_below_60(self):
        """CPI <= 60 => no TIME_BLOCK_SUGGESTION."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=40)
        recs = compute_protective_recommendations(self.user, self.now)
        time_blocks = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_TIME_BLOCK]
        self.assertEqual(len(time_blocks), 0)

    @patch('apps.core.blueprint.protective_engine._get_urgent_commitments')
    def test_renegotiation_prompt_when_breach_high(self, mock_urgent):
        """Commitment due <24h + breach >0.6 => EARLY_RENEGOTIATION_PROMPT."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=65, breach=0.7)
        mock_urgent.return_value = [
            {'id': 1, 'text': 'Submit proposal', 'time_boundary': self.now + dt.timedelta(hours=12)},
        ]

        recs = compute_protective_recommendations(self.user, self.now)
        reneg = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_RENEGOTIATION]
        self.assertGreaterEqual(len(reneg), 1)

    @patch('apps.core.blueprint.protective_engine._get_urgent_commitments')
    def test_no_renegotiation_when_breach_low(self, mock_urgent):
        """Breach < 0.6 => no EARLY_RENEGOTIATION_PROMPT."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=65, breach=0.4)
        mock_urgent.return_value = [
            {'id': 1, 'text': 'Submit proposal', 'time_boundary': self.now + dt.timedelta(hours=12)},
        ]

        recs = compute_protective_recommendations(self.user, self.now)
        reneg = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_RENEGOTIATION]
        self.assertEqual(len(reneg), 0)

    @patch('apps.core.blueprint.protective_engine._count_overloaded_days')
    def test_capacity_warning_gentle(self, mock_days):
        """1 overloaded day => gentle warning."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=50)
        mock_days.return_value = 1

        recs = compute_protective_recommendations(self.user, self.now)
        cap = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_CAPACITY_WARNING]
        self.assertEqual(len(cap), 1)
        self.assertIn('Heads up', cap[0].title)
        self.assertEqual(cap[0].metadata['severity'], 'gentle')

    @patch('apps.core.blueprint.protective_engine._count_overloaded_days')
    def test_capacity_warning_escalation(self, mock_days):
        """2 overloaded days => warning; 3+ => red alert."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=50)

        # 2 days
        mock_days.return_value = 2
        recs = compute_protective_recommendations(self.user, self.now)
        cap = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_CAPACITY_WARNING]
        self.assertEqual(len(cap), 1)
        self.assertEqual(cap[0].metadata['severity'], 'warning')

        # Clear for next test
        ProtectiveRecommendation.objects.all().delete()

        # 3+ days
        mock_days.return_value = 3
        recs = compute_protective_recommendations(self.user, self.now)
        cap = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_CAPACITY_WARNING]
        self.assertEqual(len(cap), 1)
        self.assertEqual(cap[0].metadata['severity'], 'red_alert')

    @patch('apps.core.blueprint.protective_engine._check_deadline_collisions')
    def test_focus_plan_on_collisions(self, mock_coll):
        """Collisions => DEADLINE_FOCUS_PLAN."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        self._create_pressure_snapshot(cpi=50)
        mock_coll.return_value = {
            'has_collisions': True,
            'collision_count': 2,
            'top_deadlines': [
                {'label': 'Report due'},
                {'label': 'Meeting prep'},
            ],
        }

        recs = compute_protective_recommendations(self.user, self.now)
        focus = [r for r in recs if r.recommendation_type == ProtectiveRecommendation.TYPE_FOCUS_PLAN]
        self.assertEqual(len(focus), 1)
        self.assertIn('Report due', focus[0].message)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AlertSchedulingTests(TestCase):
    """Tests for schedule_deadline_alerts."""

    def setUp(self):
        self.user = _create_test_user('alerts@test.com')
        self.now = timezone.now()
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def _create_commitment(self, text='Test commitment', hours_ahead=30):
        """Create a pending commitment for testing."""
        from apps.core.blueprint.models import Commitment
        return Commitment.objects.create(
            user=self.user,
            normalized_text=text,
            commitment_type='DO',
            time_boundary=self.now + dt.timedelta(hours=hours_ahead),
            status='pending',
        )

    def test_alerts_created_for_future_commitment(self):
        """24h/4h/1h alerts created for a commitment due in 30h."""
        from apps.core.blueprint.protective_engine import schedule_deadline_alerts
        from apps.core.blueprint.protective_models import ProtectiveAlert

        # Clear any alerts created by signals during commitment creation
        self._create_commitment(hours_ahead=30)
        ProtectiveAlert.objects.filter(user=self.user).delete()

        alerts = schedule_deadline_alerts(self.user, self.now)

        # Should create 24h, 4h, and 1h alerts
        types = {a.alert_type for a in alerts}
        self.assertIn(ProtectiveAlert.TYPE_DEADLINE_24H, types)
        self.assertIn(ProtectiveAlert.TYPE_DEADLINE_4H, types)
        self.assertIn(ProtectiveAlert.TYPE_DEADLINE_1H, types)

    def test_no_duplicate_alerts(self):
        """Running schedule_deadline_alerts twice doesn't create duplicates."""
        from apps.core.blueprint.protective_engine import schedule_deadline_alerts
        from apps.core.blueprint.protective_models import ProtectiveAlert

        self._create_commitment(hours_ahead=30)
        # Clear signal-created alerts, then run twice
        ProtectiveAlert.objects.filter(user=self.user).delete()

        alerts1 = schedule_deadline_alerts(self.user, self.now)
        alerts2 = schedule_deadline_alerts(self.user, self.now)

        self.assertGreater(len(alerts1), 0)
        self.assertEqual(len(alerts2), 0)  # No new alerts

    def test_renegotiation_cancels_old_alerts(self):
        """cancel_alerts_for_object cancels pending alerts."""
        from apps.core.blueprint.protective_engine import (
            cancel_alerts_for_object,
            schedule_deadline_alerts,
        )
        from apps.core.blueprint.protective_models import ProtectiveAlert

        c = self._create_commitment(hours_ahead=30)
        # Clear signal-created alerts, then schedule fresh
        ProtectiveAlert.objects.filter(user=self.user).delete()
        schedule_deadline_alerts(self.user, self.now)

        pending_before = ProtectiveAlert.objects.filter(
            user=self.user,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        ).count()
        self.assertGreater(pending_before, 0)

        cancelled = cancel_alerts_for_object(self.user, 'Commitment', c.id, 'renegotiated')
        self.assertEqual(cancelled, pending_before)

        pending_after = ProtectiveAlert.objects.filter(
            user=self.user,
            delivery_status=ProtectiveAlert.DELIVERY_PENDING,
        ).count()
        self.assertEqual(pending_after, 0)

    def test_no_alerts_for_past_commitments(self):
        """No alerts scheduled for commitments already past due."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.protective_engine import schedule_deadline_alerts

        Commitment.objects.create(
            user=self.user,
            normalized_text='Past commitment',
            commitment_type='DO',
            time_boundary=self.now - dt.timedelta(hours=2),
            status='pending',
        )
        alerts = schedule_deadline_alerts(self.user, self.now)
        self.assertEqual(len(alerts), 0)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class ThrottleTests(TestCase):
    """Tests for alert delivery throttle."""

    def setUp(self):
        self.user = _create_test_user('throttle@test.com')
        self.now = timezone.now()

    def test_throttle_suppression(self):
        """Alerts exceeding hourly throttle are suppressed."""
        from apps.core.blueprint.protective_engine import (
            DNE_MAX_ALERTS_PER_HOUR,
            deliver_due_alerts,
        )
        from apps.core.blueprint.protective_models import (
            ProtectiveActionLog,
            ProtectiveAlert,
        )

        # Create more alerts than hourly limit
        for i in range(DNE_MAX_ALERTS_PER_HOUR + 2):
            ProtectiveAlert.objects.create(
                user=self.user,
                alert_type=ProtectiveAlert.TYPE_DEADLINE_4H,
                message=f'Test alert {i}',
                scheduled_for=self.now - dt.timedelta(minutes=i + 1),
            )

        result = deliver_due_alerts(self.now)
        self.assertEqual(result['delivered'], DNE_MAX_ALERTS_PER_HOUR)
        self.assertEqual(result['suppressed'], 2)

        # Verify suppression logged
        suppressed_logs = ProtectiveActionLog.objects.filter(
            user=self.user,
            event_type=ProtectiveActionLog.EVENT_ALERT_SUPPRESSED,
        ).count()
        self.assertEqual(suppressed_logs, 2)

    def test_delivered_alerts_logged(self):
        """Successfully delivered alerts are logged."""
        from apps.core.blueprint.protective_engine import deliver_due_alerts
        from apps.core.blueprint.protective_models import (
            ProtectiveActionLog,
            ProtectiveAlert,
        )

        ProtectiveAlert.objects.create(
            user=self.user,
            alert_type=ProtectiveAlert.TYPE_DEADLINE_24H,
            message='Test delivery',
            scheduled_for=self.now - dt.timedelta(minutes=5),
        )

        result = deliver_due_alerts(self.now)
        self.assertEqual(result['delivered'], 1)

        delivered_logs = ProtectiveActionLog.objects.filter(
            user=self.user,
            event_type=ProtectiveActionLog.EVENT_ALERT_DELIVERED,
        ).count()
        self.assertEqual(delivered_logs, 1)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class OverloadTriggerTests(TestCase):
    """Tests for apply_overload_triggers."""

    def setUp(self):
        self.user = _create_test_user('overload@test.com')

    def _create_pressure_snapshot_raw(self, cpi):
        """Create a PressureSnapshot without triggering signals."""
        from apps.core.blueprint.pressure_models import PressureSnapshot
        # Use update_or_create pattern that avoids signal-based dedup issues
        snapshot = PressureSnapshot(
            user=self.user,
            pressure_index=cpi,
            density_score=0.5,
            compression_score=0.3,
            breach_risk_score=0.4,
            erosion_score=0.2,
            collision_score=0.1,
        )
        # Save without sending signals to isolate our tests
        PressureSnapshot.objects.bulk_create([snapshot])
        return PressureSnapshot.objects.filter(user=self.user).order_by('-computed_at').first()

    def test_cpi_above_80_creates_level_2(self):
        """CPI > 80 => InterventionLog Level 2 (Ping)."""
        from apps.core.blueprint.models import InterventionLog
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        snapshot = self._create_pressure_snapshot_raw(cpi=85)
        intervention = apply_overload_triggers(self.user, snapshot)

        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.level, InterventionLog.LEVEL_PING)
        self.assertEqual(intervention.trigger_type, 'high_load_risk')

    def test_cpi_above_90_creates_level_3(self):
        """CPI > 90 => InterventionLog Level 3 (Interrupt)."""
        from apps.core.blueprint.models import InterventionLog
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        snapshot = self._create_pressure_snapshot_raw(cpi=95)
        intervention = apply_overload_triggers(self.user, snapshot)

        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.level, InterventionLog.LEVEL_INTERRUPT)
        self.assertEqual(intervention.trigger_type, 'critical_overload_risk')

    def test_cpi_below_80_no_intervention(self):
        """CPI <= 80 => no InterventionLog created."""
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        snapshot = self._create_pressure_snapshot_raw(cpi=75)
        intervention = apply_overload_triggers(self.user, snapshot)
        self.assertIsNone(intervention)

    def test_overload_does_not_alter_escalation_state(self):
        """Overload triggers must NOT change EscalationState."""
        from apps.core.blueprint.models import EscalationState
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        # Create clean escalation state
        state = EscalationState.objects.create(
            user=self.user,
            current_level=0,  # CLEAN
        )

        snapshot = self._create_pressure_snapshot_raw(cpi=95)
        apply_overload_triggers(self.user, snapshot)

        # Refresh and verify escalation state unchanged
        state.refresh_from_db()
        self.assertEqual(state.current_level, 0)  # Still CLEAN

    def test_overload_deduplication(self):
        """Same trigger within 6 hours doesn't create duplicates."""
        from apps.core.blueprint.models import InterventionLog
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        snapshot = self._create_pressure_snapshot_raw(cpi=95)
        first = apply_overload_triggers(self.user, snapshot)
        second = apply_overload_triggers(self.user, snapshot)

        self.assertIsNotNone(first)
        self.assertIsNone(second)  # Deduped

        count = InterventionLog.objects.filter(
            user=self.user,
            trigger_type='critical_overload_risk',
        ).count()
        self.assertEqual(count, 1)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class HumanLanguageComplianceTests(TestCase):
    """Verify no technical jargon in user-facing fields."""

    def setUp(self):
        self.user = _create_test_user('language@test.com')
        self.now = timezone.now()

    def _create_pressure_snapshot(self, cpi=65, breach=0.7):
        from apps.core.blueprint.pressure_models import PressureSnapshot
        snapshot = PressureSnapshot(
            user=self.user,
            pressure_index=cpi,
            breach_risk_score=breach,
        )
        PressureSnapshot.objects.bulk_create([snapshot])
        return PressureSnapshot.objects.filter(user=self.user).order_by('-computed_at').first()

    @patch('apps.core.blueprint.protective_engine._has_free_gap', return_value=True)
    @patch('apps.core.blueprint.protective_engine._find_highest_risk_item')
    @patch('apps.core.blueprint.protective_engine._count_overloaded_days', return_value=3)
    @patch('apps.core.blueprint.protective_engine._get_urgent_commitments')
    @patch('apps.core.blueprint.protective_engine._check_deadline_collisions')
    def test_no_jargon_in_recommendations(self, mock_coll, mock_urgent, mock_days, mock_risk, mock_gap):
        """All recommendation messages must be free of technical jargon."""
        from apps.core.blueprint.protective_engine import compute_protective_recommendations

        self._create_pressure_snapshot(cpi=70, breach=0.8)
        mock_risk.return_value = {'label': 'Morning workout', 'object_type': 'NonNeg', 'object_id': 1}
        mock_urgent.return_value = [
            {'id': 1, 'text': 'Submit report', 'time_boundary': self.now + dt.timedelta(hours=12)},
        ]
        mock_coll.return_value = {
            'has_collisions': True,
            'collision_count': 2,
            'top_deadlines': [{'label': 'Deadline A'}, {'label': 'Deadline B'}],
        }

        recs = compute_protective_recommendations(self.user, self.now)

        for rec in recs:
            self.assertIsNone(
                FORBIDDEN_PATTERN.search(rec.title),
                f"Jargon found in title: '{rec.title}'",
            )
            self.assertIsNone(
                FORBIDDEN_PATTERN.search(rec.message),
                f"Jargon found in message: '{rec.message}'",
            )

    def test_no_jargon_in_alert_messages(self):
        """All alert messages must be free of technical jargon."""
        from apps.core.blueprint.protective_engine import _build_deadline_alert_message
        from apps.core.blueprint.protective_models import ProtectiveAlert

        for alert_type in [
            ProtectiveAlert.TYPE_DEADLINE_24H,
            ProtectiveAlert.TYPE_DEADLINE_4H,
            ProtectiveAlert.TYPE_DEADLINE_1H,
        ]:
            message, cta = _build_deadline_alert_message(
                alert_type, 'Test commitment', self.now + dt.timedelta(hours=24),
            )
            self.assertIsNone(
                FORBIDDEN_PATTERN.search(message),
                f"Jargon found in {alert_type} message: '{message}'",
            )

    def test_no_jargon_in_overload_messages(self):
        """InterventionLog messages from overload triggers must be clean."""
        from apps.core.blueprint.protective_engine import apply_overload_triggers

        for cpi in [85, 95]:
            from apps.core.blueprint.pressure_models import PressureSnapshot
            snapshot = PressureSnapshot.objects.create(
                user=self.user, pressure_index=cpi,
            )
            intervention = apply_overload_triggers(self.user, snapshot)
            if intervention:
                self.assertIsNone(
                    FORBIDDEN_PATTERN.search(intervention.message),
                    f"Jargon found in intervention message (CPI={cpi}): '{intervention.message}'",
                )
                # Clean up for next iteration dedup
                intervention.delete()

    def test_load_status_labels_human(self):
        """Load status labels must be human language."""
        from apps.core.blueprint.protective_engine import get_load_status_label

        labels = [
            get_load_status_label(30),
            get_load_status_label(65),
            get_load_status_label(85),
            get_load_status_label(95),
        ]
        expected = ['Normal', 'Elevated', 'High', 'Critical']
        self.assertEqual(labels, expected)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class SupersedeExpireTests(TestCase):
    """Tests for supersede/expire behavior."""

    def setUp(self):
        self.user = _create_test_user('supersede@test.com')
        self.now = timezone.now()

    def test_new_rec_within_12h_expires_old(self):
        """New recommendation of same type within 12h expires older one."""
        from apps.core.blueprint.protective_engine import expire_superseded_recommendations
        from apps.core.blueprint.protective_models import (
            ProtectiveActionLog,
            ProtectiveRecommendation,
        )

        old = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title='Old warning', message='Old',
            related_object_type='', related_object_id=None,
            created_at=self.now - dt.timedelta(hours=6),
        )
        new = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title='New warning', message='New',
            related_object_type='', related_object_id=None,
            created_at=self.now,
        )

        expired = expire_superseded_recommendations(self.user)
        self.assertEqual(expired, 1)

        old.refresh_from_db()
        self.assertEqual(old.status, ProtectiveRecommendation.STATUS_EXPIRED)

        new.refresh_from_db()
        self.assertEqual(new.status, ProtectiveRecommendation.STATUS_ACTIVE)

        # Verify audit log
        log = ProtectiveActionLog.objects.filter(
            event_type=ProtectiveActionLog.EVENT_RECOMMENDATION_EXPIRED,
        ).first()
        self.assertIsNotNone(log)

    def test_no_expire_beyond_12h(self):
        """Recommendations >12h apart are NOT expired."""
        from apps.core.blueprint.protective_engine import expire_superseded_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        old = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title='Old', message='Old',
            created_at=self.now - dt.timedelta(hours=13),
        )
        new = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title='New', message='New',
            created_at=self.now,
        )

        expired = expire_superseded_recommendations(self.user)
        self.assertEqual(expired, 0)

        old.refresh_from_db()
        self.assertEqual(old.status, ProtectiveRecommendation.STATUS_ACTIVE)

    def test_no_destructive_deletes(self):
        """Expire never deletes records — only status changes."""
        from apps.core.blueprint.protective_engine import expire_superseded_recommendations
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_FOCUS_PLAN,
            title='A', message='A',
            created_at=self.now - dt.timedelta(hours=2),
        )
        ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_FOCUS_PLAN,
            title='B', message='B',
            created_at=self.now,
        )

        count_before = ProtectiveRecommendation.objects.filter(user=self.user).count()
        expire_superseded_recommendations(self.user)
        count_after = ProtectiveRecommendation.objects.filter(user=self.user).count()

        self.assertEqual(count_before, count_after)  # No deletes


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class UserActionTests(TestCase):
    """Tests for dismiss_recommendation and accept_recommendation."""

    def setUp(self):
        self.user = _create_test_user('actions@test.com')

    def test_dismiss_recommendation(self):
        """Dismissing updates status and logs reason."""
        from apps.core.blueprint.protective_engine import dismiss_recommendation
        from apps.core.blueprint.protective_models import (
            ProtectiveActionLog,
            ProtectiveRecommendation,
        )

        rec = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
            title='Test', message='Test',
        )

        dismiss_recommendation(rec, reason='bad_timing')

        rec.refresh_from_db()
        self.assertEqual(rec.status, ProtectiveRecommendation.STATUS_DISMISSED)
        self.assertEqual(rec.dismissal_reason, 'bad_timing')

        log = ProtectiveActionLog.objects.filter(
            event_type=ProtectiveActionLog.EVENT_DISMISSED,
        ).first()
        self.assertIsNotNone(log)

    def test_accept_time_block_returns_follow_up(self):
        """Accepting TIME_BLOCK returns follow-up message."""
        from apps.core.blueprint.protective_engine import accept_recommendation
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        rec = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
            title='Test', message='Test',
        )

        follow_up = accept_recommendation(rec)
        self.assertIn('propose 3 times', follow_up)

        rec.refresh_from_db()
        self.assertEqual(rec.status, ProtectiveRecommendation.STATUS_ACCEPTED)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class ProtectiveBriefingTests(TestCase):
    """Tests for get_protective_briefing (CoS context injection)."""

    def setUp(self):
        self.user = _create_test_user('briefing@test.com')

    def test_briefing_with_no_data(self):
        """Briefing returns default structure when no data exists."""
        from apps.core.blueprint.protective_engine import get_protective_briefing

        briefing = get_protective_briefing(self.user)
        self.assertEqual(briefing['load_status'], 'Normal')
        self.assertEqual(briefing['recommendations'], [])
        self.assertEqual(briefing['upcoming_alerts'], [])

    def test_briefing_load_status_from_pressure(self):
        """Load status reflects latest pressure snapshot."""
        from apps.core.blueprint.pressure_models import PressureSnapshot
        from apps.core.blueprint.protective_engine import get_protective_briefing

        PressureSnapshot.objects.create(user=self.user, pressure_index=85)

        briefing = get_protective_briefing(self.user)
        self.assertEqual(briefing['load_status'], 'High')

    def test_briefing_includes_active_recommendations(self):
        """Briefing includes active recommendations."""
        from apps.core.blueprint.protective_engine import get_protective_briefing
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_CAPACITY_WARNING,
            title='Heavy day ahead', message='Your schedule is packed.', priority=60,
        )

        briefing = get_protective_briefing(self.user)
        self.assertEqual(len(briefing['recommendations']), 1)
        self.assertEqual(briefing['recommendations'][0]['title'], 'Heavy day ahead')

    def test_briefing_includes_upcoming_alerts(self):
        """Briefing includes alerts due in next 24h."""
        from apps.core.blueprint.protective_engine import get_protective_briefing
        from apps.core.blueprint.protective_models import ProtectiveAlert

        ProtectiveAlert.objects.create(
            user=self.user,
            alert_type=ProtectiveAlert.TYPE_DEADLINE_4H,
            message='Deadline approaching',
            scheduled_for=timezone.now() + dt.timedelta(hours=3),
        )

        briefing = get_protective_briefing(self.user)
        self.assertEqual(len(briefing['upcoming_alerts']), 1)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class ISERegistrationTests(TestCase):
    """Tests for ISE scheduler registration."""

    def test_protective_sweep_registered(self):
        """run_protective_sweep is registered in ISE."""
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks
        tasks = get_registered_tasks()
        self.assertIn('run_protective_sweep', tasks)
        self.assertEqual(tasks['run_protective_sweep']['interval_seconds'], 86400)

    def test_alert_delivery_registered(self):
        """deliver_protective_alerts is registered in ISE."""
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks
        tasks = get_registered_tasks()
        self.assertIn('deliver_protective_alerts', tasks)
        self.assertEqual(tasks['deliver_protective_alerts']['interval_seconds'], 300)


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AdvisoryOnlyTests(TestCase):
    """Verify Phase 5 is advisory-only — no auto-modifications."""

    def setUp(self):
        self.user = _create_test_user('advisory@test.com')
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        PersonalOperatingBlueprint.get_or_create_for_user(self.user)

    def test_no_commitment_auto_modification(self):
        """Recommendations never auto-change commitment status."""
        from apps.core.blueprint.models import Commitment
        from apps.core.blueprint.protective_engine import compute_protective_recommendations

        from apps.core.blueprint.pressure_models import PressureSnapshot
        PressureSnapshot.objects.create(user=self.user, pressure_index=85, breach_risk_score=0.8)

        c = Commitment.objects.create(
            user=self.user,
            normalized_text='Test commitment',
            commitment_type='DO',
            time_boundary=timezone.now() + dt.timedelta(hours=12),
            status='pending',
        )

        compute_protective_recommendations(self.user)

        c.refresh_from_db()
        self.assertEqual(c.status, 'pending')  # Unchanged

    def test_accept_does_not_auto_schedule(self):
        """Accepting a time block recommendation does NOT auto-schedule."""
        from apps.core.blueprint.protective_engine import accept_recommendation
        from apps.core.blueprint.protective_models import ProtectiveRecommendation

        rec = ProtectiveRecommendation.objects.create(
            user=self.user,
            recommendation_type=ProtectiveRecommendation.TYPE_TIME_BLOCK,
            title='Test', message='Test',
        )

        result = accept_recommendation(rec)
        # Returns a follow-up question, not an auto-action confirmation
        self.assertIn('propose', result.lower())
