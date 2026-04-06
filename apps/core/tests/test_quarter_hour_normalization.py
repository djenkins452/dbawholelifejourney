"""
Tests for 15-minute time normalization.

Verifies that normalize_to_quarter_hour() correctly rounds times
and that model save() methods enforce the constraint.
"""

import datetime

from django.test import TestCase

from apps.core.utils import normalize_to_quarter_hour


class NormalizeToQuarterHourTests(TestCase):
    """Unit tests for the normalize_to_quarter_hour utility."""

    def test_none_returns_none(self):
        self.assertIsNone(normalize_to_quarter_hour(None))

    def test_already_on_quarter_hour(self):
        """Times already on 00/15/30/45 should be unchanged."""
        for minute in (0, 15, 30, 45):
            t = datetime.time(9, minute)
            self.assertEqual(normalize_to_quarter_hour(t), t)

    def test_round_down_7_minutes(self):
        """11:07 → 11:00 (7 minutes rounds down)."""
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(11, 7)),
            datetime.time(11, 0),
        )

    def test_round_up_8_minutes(self):
        """11:08 → 11:15 (8 minutes rounds up)."""
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(11, 8)),
            datetime.time(11, 15),
        )

    def test_round_down_near_hour_boundary(self):
        """11:52 → 11:45 (7 minutes past :45 rounds down)."""
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(11, 52)),
            datetime.time(11, 45),
        )

    def test_round_up_crosses_hour(self):
        """11:53 → 12:00 (8 minutes past :45 rounds up to next hour)."""
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(11, 53)),
            datetime.time(12, 0),
        )

    def test_round_up_crosses_midnight(self):
        """23:53 → 00:00 (rounds up past 23:59 wraps to midnight)."""
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(23, 53)),
            datetime.time(0, 0),
        )

    def test_exact_boundaries(self):
        """Test exact midpoint boundaries."""
        # 7 min after quarter = round down
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(14, 22)),  # 15+7
            datetime.time(14, 15),
        )
        # 8 min after quarter = round up
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(14, 23)),  # 15+8
            datetime.time(14, 30),
        )

    def test_seconds_stripped(self):
        """Seconds should be zeroed out."""
        result = normalize_to_quarter_hour(datetime.time(9, 15, 45))
        self.assertEqual(result, datetime.time(9, 15, 0))

    def test_all_minutes_round_correctly(self):
        """Every minute 0-59 should round to one of 00/15/30/45."""
        valid_minutes = {0, 15, 30, 45}
        for minute in range(60):
            result = normalize_to_quarter_hour(datetime.time(10, minute))
            self.assertIn(
                result.minute, valid_minutes,
                f"Minute {minute} rounded to {result.minute}, expected one of {valid_minutes}",
            )

    def test_midnight(self):
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(0, 0)),
            datetime.time(0, 0),
        )

    def test_end_of_day(self):
        """23:45 stays 23:45."""
        self.assertEqual(
            normalize_to_quarter_hour(datetime.time(23, 45)),
            datetime.time(23, 45),
        )


class TaskTimeNormalizationTests(TestCase):
    """Test that Task model normalizes times on save."""

    def setUp(self):
        from django.conf import settings
        from apps.users.models import User, TermsAcceptance
        self.user = User.objects.create_user(
            email='timetest@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_task_normalizes_scheduled_time(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='Test task',
            scheduled_time=datetime.time(9, 7),
            scheduled_end_time=datetime.time(10, 53),
        )
        task.refresh_from_db()
        self.assertEqual(task.scheduled_time, datetime.time(9, 0))
        self.assertEqual(task.scheduled_end_time, datetime.time(11, 0))

    def test_task_none_times_stay_none(self):
        from apps.life.models import Task
        task = Task.objects.create(
            user=self.user,
            title='No time task',
        )
        task.refresh_from_db()
        self.assertIsNone(task.scheduled_time)
        self.assertIsNone(task.scheduled_end_time)


class LifeEventTimeNormalizationTests(TestCase):
    """Test that LifeEvent model normalizes times on save."""

    def setUp(self):
        from django.conf import settings
        from apps.users.models import User, TermsAcceptance
        self.user = User.objects.create_user(
            email='eventtime@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_event_normalizes_times(self):
        from apps.life.models import LifeEvent
        event = LifeEvent.objects.create(
            user=self.user,
            title='Test event',
            start_date=datetime.date.today(),
            start_time=datetime.time(14, 8),
            end_time=datetime.time(15, 22),
        )
        event.refresh_from_db()
        self.assertEqual(event.start_time, datetime.time(14, 15))
        self.assertEqual(event.end_time, datetime.time(15, 15))


class RoutineScheduleTimeNormalizationTests(TestCase):
    """Test that RoutineSchedule model normalizes times on save."""

    def setUp(self):
        from django.conf import settings
        from apps.users.models import User, TermsAcceptance
        self.user = User.objects.create_user(
            email='routinetime@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_routine_schedule_normalizes_time(self):
        from apps.life.models import Routine, RoutineSchedule
        routine = Routine.objects.create(
            user=self.user,
            name='Morning Routine',
            time_of_day='morning',
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name='Prayer',
            scheduled_time=datetime.time(6, 22),
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.scheduled_time, datetime.time(6, 15))


class MedicineScheduleTimeNormalizationTests(TestCase):
    """Test that MedicineSchedule model normalizes times on save."""

    def setUp(self):
        from django.conf import settings
        from apps.users.models import User, TermsAcceptance
        self.user = User.objects.create_user(
            email='medtime@example.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_medicine_schedule_normalizes_time(self):
        from apps.health.models import Intake, IntakeSchedule
        medicine = Intake.objects.create(
            user=self.user,
            name='Test Med',
            start_date=datetime.date.today(),
        )
        schedule = IntakeSchedule.objects.create(
            intake=medicine,
            scheduled_time=datetime.time(8, 7),
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.scheduled_time, datetime.time(8, 0))
