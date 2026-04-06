# ==============================================================================
# File: apps/core/ai_events/tests/test_resolver.py
# Project: Whole Life Journey
# Description: Tests for cross-domain EventResolver
# ==============================================================================

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_events.resolver import EventResolver
from apps.health.models import Intake, IntakeLog, IntakeSchedule, WorkoutSession
from apps.users.models import User, TermsAcceptance


class EventResolverTestBase(TestCase):
    """Base class with test user setup."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='testresolve@example.com',
            password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.resolver = EventResolver()


class ResolverMedicationTest(EventResolverTestBase):
    """Test EventResolver medication queries."""

    def setUp(self):
        super().setUp()
        self.medicine = Intake.objects.create(
            user=self.user,
            name='Metformin',
            dose='500mg',
            frequency='daily',
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date.today() - timedelta(days=30),
        )
        self.schedule = IntakeSchedule.objects.create(
            intake=self.medicine,
            scheduled_time=time(12, 0),
            time_of_day='lunch',
            is_active=True,
        )

    def test_get_missed_events_medication(self):
        yesterday = date.today() - timedelta(days=1)
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=yesterday,
            scheduled_time=time(12, 0),
            log_status=IntakeLog.STATUS_MISSED,
        )
        missed = self.resolver.get_missed_events(
            self.user, 'medication',
            yesterday, date.today(),
        )
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0].domain, 'medication')
        self.assertEqual(missed[0].detail['medicine_name'], 'Metformin')


class ResolverCrossDomainTest(EventResolverTestBase):
    """Test cross-domain queries."""

    def setUp(self):
        super().setUp()
        self.medicine = Intake.objects.create(
            user=self.user,
            name='Aspirin',
            dose='81mg',
            frequency='daily',
            intake_status=Intake.STATUS_ACTIVE,
            start_date=date.today() - timedelta(days=30),
        )
        self.schedule = IntakeSchedule.objects.create(
            intake=self.medicine,
            scheduled_time=time(8, 0),
            time_of_day='morning',
            is_active=True,
        )

    def test_get_all_missed_includes_medication(self):
        yesterday = date.today() - timedelta(days=1)
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=yesterday,
            scheduled_time=time(8, 0),
            log_status=IntakeLog.STATUS_MISSED,
        )
        missed = self.resolver.get_all_missed(
            self.user,
            yesterday, date.today(),
        )
        med_missed = [e for e in missed if e.domain == 'medication']
        self.assertGreaterEqual(len(med_missed), 1)

    def test_day_timeline_includes_medication_and_workout(self):
        today = date.today()

        # Medication event
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(8, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now(),
        )

        # Workout event
        WorkoutSession.objects.create(
            user=self.user,
            date=today,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            duration_minutes=45,
        )

        events = self.resolver.get_day_timeline(self.user, today)
        domains = {e.domain for e in events}
        self.assertIn('medication', domains)
        self.assertIn('workout', domains)

    def test_day_timeline_sorted_by_timestamp(self):
        today = date.today()

        # Morning med
        IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=today,
            scheduled_time=time(8, 0),
            log_status=IntakeLog.STATUS_TAKEN,
            taken_at=timezone.now().replace(hour=8),
        )

        # Afternoon workout
        WorkoutSession.objects.create(
            user=self.user,
            date=today,
            started_at=timezone.now().replace(hour=14),
            completed_at=timezone.now().replace(hour=15),
            duration_minutes=60,
        )

        events = self.resolver.get_day_timeline(self.user, today)
        self.assertGreaterEqual(len(events), 2)
        # Verify sorted
        for i in range(1, len(events)):
            self.assertGreaterEqual(events[i].timestamp, events[i - 1].timestamp)

    def test_empty_day_returns_empty_list(self):
        old_date = date.today() - timedelta(days=20)
        events = self.resolver.get_day_timeline(self.user, old_date)
        self.assertEqual(events, [])


class ResolverUnknownDomainTest(EventResolverTestBase):
    """Test error handling for unknown domains."""

    def test_unknown_domain_raises(self):
        with self.assertRaises(ValueError):
            self.resolver.get_events(
                self.user, 'nonexistent',
                date.today() - timedelta(days=7), date.today(),
            )
