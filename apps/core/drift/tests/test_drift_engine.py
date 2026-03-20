"""
Phase 10 — Drift Engine Tests.

Tests:
1) Small shifts (<15 min) produce no instability
2) 3 shifts of 90 min with protected events → escalation triggered
3) Shifts affecting non-Tier events only → no escalation
4) Same window duplicate trigger prevented
5) PostgreSQL transaction safety (no aborted state)
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.utils.idempotency import compute_idempotency_key
from apps.core.ai_state.models import UserState
from apps.core.drift.engine import DriftEngine
from apps.core.drift.models import DriftSignal, ExecutionLog
from apps.core.drift.weights import compute_schedule_change_weight

User = get_user_model()


class WeightCalculationTests(TestCase):
    """Deterministic weight rule verification."""

    def _noon(self):
        """Fixed noon time to avoid midnight-crossing race conditions."""
        return timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)

    def test_small_shift_under_15_min(self):
        base = self._noon()
        result = compute_schedule_change_weight(base, base + dt.timedelta(minutes=10))
        self.assertEqual(result['weight'], 5)
        self.assertEqual(result['instability_points'], 0)

    def test_shift_15_to_59_min(self):
        base = self._noon()
        result = compute_schedule_change_weight(base, base + dt.timedelta(minutes=30))
        self.assertEqual(result['weight'], 20)
        self.assertEqual(result['instability_points'], 1)

    def test_shift_60_to_179_min(self):
        base = self._noon()
        result = compute_schedule_change_weight(base, base + dt.timedelta(minutes=90))
        self.assertEqual(result['weight'], 45)
        self.assertEqual(result['instability_points'], 3)

    def test_shift_180_plus_min(self):
        base = self._noon()
        result = compute_schedule_change_weight(base, base + dt.timedelta(minutes=200))
        self.assertEqual(result['weight'], 75)
        self.assertEqual(result['instability_points'], 5)

    def test_date_change_override(self):
        base = self._noon()
        next_day = base + dt.timedelta(days=1)
        result = compute_schedule_change_weight(base, next_day)
        self.assertTrue(result['date_changed'])
        self.assertGreaterEqual(result['weight'], 60)
        self.assertGreaterEqual(result['instability_points'], 4)

    def test_boundary_14_min(self):
        base = self._noon()
        result = compute_schedule_change_weight(base, base + dt.timedelta(minutes=14))
        self.assertEqual(result['instability_points'], 0)

    def test_boundary_15_min(self):
        base = self._noon()
        result = compute_schedule_change_weight(base, base + dt.timedelta(minutes=15))
        self.assertEqual(result['instability_points'], 1)


class DriftEngineTestMixin:
    """Shared setup for drift engine tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='drift-test@example.com',
            password='testpass123',
        )
        # Fixed noon time to avoid midnight-crossing race conditions in CI
        self.now = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)

    def _create_event(self, title='Test Event', protected=False, source_type='none', source_id=''):
        start = self.now + dt.timedelta(hours=1)
        end = start + dt.timedelta(hours=1)
        return CalendarEvent.objects.create(
            user=self.user,
            title=title,
            start_dt=start,
            end_dt=end,
            is_protected=protected,
            source_type=source_type,
            source_id=source_id,
            idempotency_key=compute_idempotency_key(
                self.user.id, title, start, end_dt=end,
            ),
        )


class SmallShiftsNoInstabilityTest(DriftEngineTestMixin, TestCase):
    """Test 1: 3 small shifts (<15 min) produce no instability points."""

    def test_three_small_shifts_no_escalation(self):
        for i in range(3):
            event = self._create_event(title=f'Small Shift {i}')
            old_start = event.start_dt
            new_start = old_start + dt.timedelta(minutes=10)

            DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )

        # All logs should have instability_points=0
        logs = ExecutionLog.objects.filter(user=self.user)
        self.assertEqual(logs.count(), 3)
        for log in logs:
            self.assertEqual(log.instability_points, 0)

        # No DriftSignal created
        self.assertEqual(DriftSignal.objects.filter(user=self.user).count(), 0)

        # UserState not created (no instability points triggered evaluation)
        self.assertFalse(UserState.objects.filter(user=self.user).exists())


class LargeShiftsEscalationTest(DriftEngineTestMixin, TestCase):
    """Test 2: 3 shifts of 90 min with protected events → escalation triggered."""

    def test_three_90min_shifts_protected_escalation(self):
        for i in range(3):
            event = self._create_event(
                title=f'Protected Shift {i}',
                protected=True,
            )
            old_start = event.start_dt
            new_start = old_start + dt.timedelta(minutes=90)

            DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )

        # Total instability: 3 * 3 = 9 points >= threshold(8)
        logs = ExecutionLog.objects.filter(user=self.user)
        self.assertEqual(logs.count(), 3)
        total = sum(l.instability_points for l in logs)
        self.assertEqual(total, 9)

        # DriftSignal should be created
        signals = DriftSignal.objects.filter(user=self.user)
        self.assertEqual(signals.count(), 1)
        self.assertEqual(
            signals.first().signal_type,
            DriftSignal.SIGNAL_SCHEDULE_INSTABILITY,
        )

        # UserState reflects score
        state = UserState.objects.get(user=self.user)
        self.assertEqual(state.schedule_instability_score, 9)


class NonTierEventsNoEscalationTest(DriftEngineTestMixin, TestCase):
    """Test 3: Shifts affecting non-Tier, non-protected events → no escalation."""

    def test_large_shifts_non_protected_no_escalation(self):
        for i in range(3):
            event = self._create_event(
                title=f'Regular Event {i}',
                protected=False,
            )
            old_start = event.start_dt
            new_start = old_start + dt.timedelta(minutes=90)

            DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )

        # Points are logged
        logs = ExecutionLog.objects.filter(user=self.user)
        total_pts = sum(l.instability_points for l in logs)
        self.assertEqual(total_pts, 9)

        # But no signal — no high-priority involvement
        self.assertEqual(DriftSignal.objects.filter(user=self.user).count(), 0)


class DuplicateWindowPreventionTest(DriftEngineTestMixin, TestCase):
    """Test 4: Same window duplicate trigger prevented."""

    def test_duplicate_signal_prevented(self):
        # Create enough protected shifts to trigger escalation
        for i in range(3):
            event = self._create_event(
                title=f'Dup Test {i}',
                protected=True,
            )
            old_start = event.start_dt
            new_start = old_start + dt.timedelta(minutes=90)
            DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )

        self.assertEqual(DriftSignal.objects.filter(user=self.user).count(), 1)

        # Add more shifts — same window, should not create another signal
        for i in range(3, 6):
            event = self._create_event(
                title=f'Dup Test Extra {i}',
                protected=True,
            )
            old_start = event.start_dt
            new_start = old_start + dt.timedelta(minutes=120)
            DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )

        # Still only 1 signal
        self.assertEqual(DriftSignal.objects.filter(user=self.user).count(), 1)


class IdempotencyDeduplicationTest(DriftEngineTestMixin, TestCase):
    """Same change recorded twice produces only one log."""

    def test_duplicate_change_deduplicated(self):
        event = self._create_event(title='Idem Test', protected=True)
        old_start = event.start_dt
        new_start = old_start + dt.timedelta(minutes=60)

        log1 = DriftEngine.record_schedule_change(
            self.user, event, old_start, new_start,
        )
        log2 = DriftEngine.record_schedule_change(
            self.user, event, old_start, new_start,
        )

        self.assertIsNotNone(log1)
        self.assertIsNone(log2)
        self.assertEqual(
            ExecutionLog.objects.filter(user=self.user).count(), 1,
        )


class TransactionSafetyTest(DriftEngineTestMixin, TestCase):
    """Test 5: PostgreSQL transaction not aborted during evaluation."""

    def test_drift_engine_inside_atomic(self):
        """Verify DriftEngine works inside an outer atomic block."""
        event = self._create_event(title='Atomic Test', protected=True)
        old_start = event.start_dt
        new_start = old_start + dt.timedelta(minutes=90)

        with transaction.atomic():
            log = DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )
            self.assertIsNotNone(log)

            # Verify we can still query after DriftEngine ran
            count = ExecutionLog.objects.filter(user=self.user).count()
            self.assertEqual(count, 1)

        # After atomic block, data persisted
        self.assertEqual(
            ExecutionLog.objects.filter(user=self.user).count(), 1,
        )

    def test_drift_engine_duplicate_inside_atomic_no_abort(self):
        """
        Duplicate idempotency hit inside atomic must not abort
        the outer transaction.
        """
        event = self._create_event(title='Atomic Dup', protected=True)
        old_start = event.start_dt
        new_start = old_start + dt.timedelta(minutes=90)

        with transaction.atomic():
            DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )
            # Second call with same params — should return None, not blow up
            result = DriftEngine.record_schedule_change(
                self.user, event, old_start, new_start,
            )
            self.assertIsNone(result)

            # Transaction still alive — can query
            self.assertEqual(
                ExecutionLog.objects.filter(user=self.user).count(), 1,
            )
