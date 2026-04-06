# ==============================================================================
# File: apps/core/ai_events/tests/test_medication_adapter.py
# Project: Whole Life Journey
# Description: Tests for medication event adapter
# ==============================================================================

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_events.adapters.medication import (
    get_day_events,
    get_events,
    get_late_events,
    get_missed_events,
    get_skipped_events,
)
from apps.health.models import Intake, IntakeLog, IntakeSchedule
from apps.users.models import User, TermsAcceptance


class MedicationAdapterTestBase(TestCase):
    """Base class with test user and medicine setup."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='testmed@example.com',
            password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        # Create test medicine
        self.medicine = Intake.objects.create(
            user=self.user,
            name='Lantus SoloStar',
            dose='10 units',
            frequency='daily',
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date.today() - timedelta(days=30),
        )

        # Create schedule
        self.schedule = IntakeSchedule.objects.create(
            intake=self.medicine,
            scheduled_time=time(9, 0),
            time_of_day='morning',
            is_active=True,
        )


class MedicationAdapterGetEventsTest(MedicationAdapterTestBase):
    """Test get_events returns all medication events in range."""

    def test_returns_empty_for_no_logs(self):
        today = date.today()
        events = get_events(self.user, today - timedelta(days=7), today)
        self.assertEqual(len(events), 0)

    def test_returns_taken_event(self):
        today = date.today()
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            taken_at=timezone.now(),
            log_status=IntakeLog.STATUS_TAKEN,
        )
        events = get_events(self.user, today, today)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].domain, 'medication')
        self.assertEqual(events[0].event_type, 'dose_taken')
        self.assertEqual(events[0].status, 'taken')
        self.assertIn('Lantus SoloStar', events[0].label)

    def test_returns_missed_event(self):
        yesterday = date.today() - timedelta(days=1)
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=yesterday,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_MISSED,
        )
        events = get_events(self.user, yesterday, yesterday)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, 'dose_missed')
        self.assertEqual(events[0].status, 'missed')

    def test_returns_multiple_events_sorted(self):
        today = date.today()
        yesterday = today - timedelta(days=1)

        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=yesterday,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now() - timedelta(days=1),
        )
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_MISSED,
        )

        events = get_events(self.user, yesterday, today)
        self.assertEqual(len(events), 2)
        # Sorted by date then time
        self.assertEqual(events[0].detail['scheduled_date'], str(yesterday))
        self.assertEqual(events[1].detail['scheduled_date'], str(today))

    def test_respects_date_bounds(self):
        """Events outside the range should not be returned."""
        old_date = date.today() - timedelta(days=15)
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=old_date,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now() - timedelta(days=15),
        )
        today = date.today()
        events = get_events(self.user, today - timedelta(days=7), today)
        self.assertEqual(len(events), 0)


class MedicationAdapterMissedTest(MedicationAdapterTestBase):
    """Test get_missed_events returns only missed doses."""

    def test_returns_only_missed(self):
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Taken yesterday
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=yesterday,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now() - timedelta(days=1),
        )
        # Missed today
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_MISSED,
        )

        missed = get_missed_events(self.user, yesterday, today)
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0].status, 'missed')
        self.assertEqual(missed[0].detail['scheduled_date'], str(today))

    def test_empty_when_nothing_missed(self):
        today = date.today()
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now(),
        )
        missed = get_missed_events(self.user, today, today)
        self.assertEqual(len(missed), 0)


class MedicationAdapterEventRecordTest(MedicationAdapterTestBase):
    """Test that EventRecord fields are correctly populated."""

    def test_event_record_has_medicine_name_in_detail(self):
        today = date.today()
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_MISSED,
        )
        events = get_missed_events(self.user, today, today)
        self.assertEqual(events[0].detail['medicine_name'], 'Lantus SoloStar')
        self.assertEqual(events[0].detail['dose'], '10 units')
        self.assertEqual(events[0].source_model, 'MedicineLog')
        self.assertIsNotNone(events[0].source_id)

    def test_event_record_has_taken_at_when_taken(self):
        today = date.today()
        taken_time = timezone.now()
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=taken_time,
        )
        events = get_events(self.user, today, today)
        self.assertIn('taken_at', events[0].detail)

    def test_label_includes_medicine_name_and_time(self):
        today = date.today()
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(9, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now(),
        )
        events = get_events(self.user, today, today)
        self.assertIn('Lantus SoloStar', events[0].label)
        self.assertIn('9:00 AM', events[0].label)


class MedicationAdapterBoundsTest(MedicationAdapterTestBase):
    """Test query boundary enforcement."""

    def test_rejects_range_over_30_days(self):
        today = date.today()
        with self.assertRaises(ValueError):
            get_events(self.user, today - timedelta(days=31), today)

    def test_rejects_end_before_start(self):
        today = date.today()
        with self.assertRaises(ValueError):
            get_events(self.user, today, today - timedelta(days=1))

    def test_allows_30_day_range(self):
        today = date.today()
        # Should not raise
        events = get_events(self.user, today - timedelta(days=30), today)
        self.assertIsInstance(events, list)
