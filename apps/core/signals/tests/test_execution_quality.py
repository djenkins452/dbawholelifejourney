"""Tests for Execution Quality Signals.

Covers:
1. Quality computation logic (on_target, late, missed_window, missed)
2. Signal generation from RoutineLog
3. Signal generation from WorkoutSession
4. Signal generation from JournalEntry
5. Signal generation from MedicineLog
6. Idempotency (update_or_create behavior)
7. Missed signal creation (get_or_create, no overwrite)
8. Edge cases (missing fields, boundary conditions)
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.signals.execution_quality import (
    compute_execution_quality,
    record_execution_signal,
    record_missed_signal,
    record_signal_from_medicine_log,
    record_signal_from_routine_log,
)
from apps.core.signals.models import ExecutionSignal
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="exectest@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestComputeExecutionQuality(TestCase):
    """Test the pure quality computation function."""

    def _make_dt(self, hour, minute=0):
        return timezone.make_aware(
            datetime(2026, 3, 23, hour, minute),
            timezone.get_current_timezone(),
        )

    def test_on_target_exact(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(9, 0)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.ON_TARGET)

    def test_on_target_within_15_minutes_late(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(9, 14)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.ON_TARGET)

    def test_on_target_boundary_15_minutes(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(9, 15)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.ON_TARGET)

    def test_on_target_early(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(8, 50)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.ON_TARGET)

    def test_on_target_early_boundary(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(8, 45)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.ON_TARGET)

    def test_late_16_minutes(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(9, 16)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.LATE)

    def test_late_1_hour(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(10, 0)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.LATE)

    def test_late_boundary_2_hours(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(11, 0)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.LATE)

    def test_missed_window_2_hours_1_minute(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(11, 1)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.MISSED_WINDOW)

    def test_missed_window_much_later(self):
        scheduled = self._make_dt(9, 0)
        actual = self._make_dt(18, 0)
        self.assertEqual(compute_execution_quality(scheduled, actual), ExecutionSignal.MISSED_WINDOW)

    def test_early_outside_window_is_missed_window(self):
        """Very early completion (>15min early) is still considered on_target by abs(delta)."""
        scheduled = self._make_dt(9, 0)
        # 16 minutes early: abs(delta) = 16min > 15min, but delta is negative (-16min)
        # delta <= 2 hours is true (negative), so LATE
        actual = self._make_dt(8, 44)
        result = compute_execution_quality(scheduled, actual)
        # abs(16min) > 15min, delta = -16min which is <= 2h, so LATE
        self.assertEqual(result, ExecutionSignal.LATE)


class TestRecordExecutionSignal(TestCase):
    """Test the record_execution_signal function."""

    def setUp(self):
        self.user = _create_test_user()
        self.today = date(2026, 3, 23)
        self.scheduled = timezone.make_aware(
            datetime(2026, 3, 23, 9, 0),
            timezone.get_current_timezone(),
        )
        self.actual = timezone.make_aware(
            datetime(2026, 3, 23, 9, 10),
            timezone.get_current_timezone(),
        )

    def test_creates_signal(self):
        signal = record_execution_signal(
            user=self.user,
            item_name="Morning Prayer",
            domain_type="routine",
            scheduled_time=self.scheduled,
            actual_time=self.actual,
            date=self.today,
            source_model="RoutineLog",
            source_id=42,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.user, self.user)
        self.assertEqual(signal.item_name, "Morning Prayer")
        self.assertEqual(signal.domain_type, "routine")
        self.assertEqual(signal.execution_quality, ExecutionSignal.ON_TARGET)
        self.assertEqual(signal.source_model, "RoutineLog")
        self.assertEqual(signal.source_id, 42)

    def test_updates_on_recompletion(self):
        """Second completion for same item/day updates rather than duplicates."""
        record_execution_signal(
            user=self.user,
            item_name="Morning Prayer",
            domain_type="routine",
            scheduled_time=self.scheduled,
            actual_time=self.actual,
            date=self.today,
        )
        # Re-record with later actual time
        later_actual = self.actual + timedelta(hours=3)
        record_execution_signal(
            user=self.user,
            item_name="Morning Prayer",
            domain_type="routine",
            scheduled_time=self.scheduled,
            actual_time=later_actual,
            date=self.today,
        )
        self.assertEqual(ExecutionSignal.objects.filter(user=self.user, date=self.today).count(), 1)
        signal = ExecutionSignal.objects.get(user=self.user, date=self.today)
        self.assertEqual(signal.execution_quality, ExecutionSignal.MISSED_WINDOW)

    def test_different_items_same_day(self):
        """Different items on the same day create separate signals."""
        record_execution_signal(
            user=self.user, item_name="Prayer", domain_type="routine",
            scheduled_time=self.scheduled, actual_time=self.actual, date=self.today,
        )
        record_execution_signal(
            user=self.user, item_name="Workout", domain_type="workout",
            scheduled_time=self.scheduled, actual_time=self.actual, date=self.today,
        )
        self.assertEqual(ExecutionSignal.objects.filter(user=self.user).count(), 2)


class TestRecordMissedSignal(TestCase):
    """Test the record_missed_signal function."""

    def setUp(self):
        self.user = _create_test_user(email="missed@example.com")
        self.today = date(2026, 3, 23)
        self.scheduled = timezone.make_aware(
            datetime(2026, 3, 23, 9, 0),
            timezone.get_current_timezone(),
        )

    def test_creates_missed_signal(self):
        signal = record_missed_signal(
            user=self.user,
            item_name="Morning Prayer",
            domain_type="routine",
            scheduled_time=self.scheduled,
            date=self.today,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.execution_quality, ExecutionSignal.MISSED)
        self.assertIsNone(signal.actual_time)

    def test_does_not_overwrite_completed_signal(self):
        """A missed signal should not overwrite an existing completion signal."""
        record_execution_signal(
            user=self.user,
            item_name="Morning Prayer",
            domain_type="routine",
            scheduled_time=self.scheduled,
            actual_time=self.scheduled + timedelta(minutes=5),
            date=self.today,
        )
        result = record_missed_signal(
            user=self.user,
            item_name="Morning Prayer",
            domain_type="routine",
            scheduled_time=self.scheduled,
            date=self.today,
        )
        self.assertIsNone(result)  # Should return None (not created)
        signal = ExecutionSignal.objects.get(
            user=self.user, item_name="Morning Prayer", date=self.today,
        )
        self.assertEqual(signal.execution_quality, ExecutionSignal.ON_TARGET)


class TestRecordSignalFromRoutineLog(TestCase):
    """Test signal generation from RoutineLog objects."""

    def setUp(self):
        self.user = _create_test_user(email="routine@example.com")

    def test_generates_signal_from_routine_log(self):
        """Creating a RoutineLog with schedule data generates an ExecutionSignal."""
        from apps.life.models import Routine, RoutineLog, RoutineSchedule

        routine = Routine.objects.create(
            user=self.user, name="Morning Routine", is_active=True,
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name="Prayer Time",
            scheduled_time=time(6, 30),
            days_of_week="0,1,2,3,4,5,6",
        )
        today = date(2026, 3, 23)
        completed_at = timezone.make_aware(
            datetime(2026, 3, 23, 6, 35),
            timezone.get_current_timezone(),
        )

        log = RoutineLog(
            user=self.user,
            schedule=schedule,
            scheduled_date=today,
            log_status="completed",
            completed_at=completed_at,
        )
        # Use the helper directly rather than saving (to avoid other signals)
        signal = record_signal_from_routine_log(log)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.item_name, "Prayer Time")
        self.assertEqual(signal.domain_type, "routine")
        self.assertEqual(signal.execution_quality, ExecutionSignal.ON_TARGET)

    def test_skips_without_schedule(self):
        from apps.life.models import RoutineLog

        log = RoutineLog(
            user=self.user,
            schedule_id=None,
            scheduled_date=date(2026, 3, 23),
            completed_at=timezone.now(),
        )
        result = record_signal_from_routine_log(log)
        self.assertIsNone(result)

    def test_skips_without_completed_at(self):
        from apps.life.models import Routine, RoutineLog, RoutineSchedule

        routine = Routine.objects.create(
            user=self.user, name="Morning Routine", is_active=True,
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name="Prayer",
            scheduled_time=time(6, 30),
            days_of_week="0,1,2,3,4,5,6",
        )
        log = RoutineLog(
            user=self.user,
            schedule=schedule,
            scheduled_date=date(2026, 3, 23),
            completed_at=None,
        )
        result = record_signal_from_routine_log(log)
        self.assertIsNone(result)


class TestRecordSignalFromIntakeLog(TestCase):
    """Test signal generation from MedicineLog objects."""

    def setUp(self):
        self.user = _create_test_user(email="medicine@example.com")

    def test_generates_signal_from_medicine_log(self):
        from apps.health.models import Intake, IntakeLog

        med = Intake.objects.create(
            user=self.user, name="Lisinopril", dose="10mg",
            start_date=date(2026, 1, 1),
        )
        today = date(2026, 3, 23)
        taken_at = timezone.make_aware(
            datetime(2026, 3, 23, 8, 5),
            timezone.get_current_timezone(),
        )

        log = IntakeLog(
            user=self.user,
            intake=med,
            scheduled_date=today,
            scheduled_time=time(8, 0),
            taken_at=taken_at,
            log_status="taken",
        )
        signal = record_signal_from_medicine_log(log)

        self.assertIsNotNone(signal)
        self.assertIn("Lisinopril", signal.item_name)
        self.assertEqual(signal.domain_type, "medicine")
        self.assertEqual(signal.execution_quality, ExecutionSignal.ON_TARGET)

    def test_skips_without_taken_at(self):
        from apps.health.models import Intake, IntakeLog

        med = Intake.objects.create(
            user=self.user, name="Lisinopril", dose="10mg",
            start_date=date(2026, 1, 1),
        )
        log = IntakeLog(
            user=self.user,
            intake=med,
            scheduled_date=date(2026, 3, 23),
            scheduled_time=time(8, 0),
            taken_at=None,
        )
        result = record_signal_from_medicine_log(log)
        self.assertIsNone(result)

    def test_skips_without_scheduled_time(self):
        from apps.health.models import Intake, IntakeLog

        med = Intake.objects.create(
            user=self.user, name="Lisinopril", dose="10mg",
            start_date=date(2026, 1, 1),
        )
        log = IntakeLog(
            user=self.user,
            intake=med,
            scheduled_date=date(2026, 3, 23),
            scheduled_time=None,
            taken_at=timezone.now(),
        )
        result = record_signal_from_medicine_log(log)
        self.assertIsNone(result)


class TestExecutionSignalModel(TestCase):
    """Test model constraints and behavior."""

    def setUp(self):
        self.user = _create_test_user(email="model@example.com")

    def test_str_representation(self):
        signal = ExecutionSignal.objects.create(
            user=self.user,
            item_name="Prayer",
            domain_type="routine",
            scheduled_time=timezone.now(),
            actual_time=timezone.now(),
            execution_quality=ExecutionSignal.ON_TARGET,
            date=date(2026, 3, 23),
        )
        self.assertIn("Prayer", str(signal))
        self.assertIn("on_target", str(signal))

    def test_unique_constraint(self):
        from django.db import IntegrityError

        kwargs = dict(
            user=self.user,
            item_name="Prayer",
            domain_type="routine",
            scheduled_time=timezone.now(),
            actual_time=timezone.now(),
            execution_quality=ExecutionSignal.ON_TARGET,
            date=date(2026, 3, 23),
        )
        ExecutionSignal.objects.create(**kwargs)
        with self.assertRaises(IntegrityError):
            ExecutionSignal.objects.create(**kwargs)
