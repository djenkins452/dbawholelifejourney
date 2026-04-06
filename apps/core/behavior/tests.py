"""
Tests for the behavior score system.

Tests cover:
  1. Shared status engine (compute_occurrence_status, adherence math)
  2. Medication domain adapter
  3. Workout domain adapter
  4. Routine domain adapter
  5. Behavior score engine (composite)
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.behavior.status_engine import (
    compute_occurrence_status,
    compute_adherence_from_counts,
    build_behavior_output,
)


class StatusEngineTest(TestCase):
    """Tests for compute_occurrence_status()."""

    def _make_dt(self, hour, minute=0):
        return timezone.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    def test_completed_on_time(self):
        scheduled = self._make_dt(8, 0)
        log = {'completed_at': scheduled + timedelta(minutes=10)}
        status = compute_occurrence_status(
            now=scheduled + timedelta(hours=1),
            scheduled_datetime=scheduled,
            grace_minutes=30,
            log=log,
        )
        self.assertEqual(status, 'completed')

    def test_completed_late(self):
        scheduled = self._make_dt(8, 0)
        log = {'completed_at': scheduled + timedelta(minutes=60)}
        status = compute_occurrence_status(
            now=scheduled + timedelta(hours=2),
            scheduled_datetime=scheduled,
            grace_minutes=30,
            log=log,
        )
        self.assertEqual(status, 'completed_late')

    def test_upcoming(self):
        scheduled = self._make_dt(20, 0)
        now = self._make_dt(18, 0)
        status = compute_occurrence_status(now, scheduled, grace_minutes=30)
        self.assertEqual(status, 'upcoming')

    def test_past_due_within_grace(self):
        scheduled = self._make_dt(8, 0)
        now = scheduled + timedelta(minutes=15)
        status = compute_occurrence_status(now, scheduled, grace_minutes=30)
        self.assertEqual(status, 'past_due')

    def test_late_after_grace(self):
        scheduled = self._make_dt(8, 0)
        now = scheduled + timedelta(minutes=45)
        status = compute_occurrence_status(now, scheduled, grace_minutes=30)
        self.assertEqual(status, 'late')


class AdherenceCalculationTest(TestCase):
    """Tests for adherence scoring math."""

    def test_perfect_score(self):
        result = compute_adherence_from_counts(
            expected=10, completed=10, late=0, skipped=0, missed=0
        )
        self.assertEqual(result['adherence'], 100.0)
        self.assertEqual(result['on_time_rate'], 100.0)

    def test_all_late(self):
        result = compute_adherence_from_counts(
            expected=10, completed=0, late=10, skipped=0, missed=0
        )
        self.assertEqual(result['adherence'], 70.0)
        self.assertEqual(result['on_time_rate'], 0.0)

    def test_mixed(self):
        # 5 completed (5.0) + 3 late (2.1) + 2 missed (0) = 7.1 / 10 = 71%
        result = compute_adherence_from_counts(
            expected=10, completed=5, late=3, skipped=0, missed=2
        )
        self.assertEqual(result['adherence'], 71.0)

    def test_all_missed(self):
        result = compute_adherence_from_counts(
            expected=5, completed=0, late=0, skipped=0, missed=5
        )
        self.assertEqual(result['adherence'], 0.0)

    def test_zero_expected(self):
        result = compute_adherence_from_counts(
            expected=0, completed=0, late=0, skipped=0, missed=0
        )
        self.assertIsNone(result['adherence'])

    def test_on_time_rate_mixed(self):
        result = compute_adherence_from_counts(
            expected=10, completed=7, late=3, skipped=0, missed=0
        )
        self.assertEqual(result['on_time_rate'], 70.0)


class BuildBehaviorOutputTest(TestCase):
    """Tests for build_behavior_output contract."""

    def test_output_shape(self):
        output = build_behavior_output(
            domain='medication',
            expected=10, completed=8, late=1, skipped=0, missed=1,
        )
        self.assertEqual(output['domain'], 'medication')
        self.assertEqual(output['expected'], 10)
        self.assertEqual(output['completed'], 8)
        self.assertEqual(output['late'], 1)
        self.assertEqual(output['skipped'], 0)
        self.assertEqual(output['missed'], 1)
        self.assertIn('adherence', output)
        self.assertIn('on_time_rate', output)


class MedicationDomainTest(TestCase):
    """Tests for calculate_medicine_behavior_output."""

    def setUp(self):
        from apps.users.models import User, TermsAcceptance
        self.user = User.objects.create_user(
            email='med_behavior@test.com', password='test123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_no_medicines_returns_none(self):
        from apps.core.behavior.domain_medication import calculate_medicine_behavior_output
        result = calculate_medicine_behavior_output(
            self.user, date.today() - timedelta(days=7), date.today()
        )
        self.assertIsNone(result)

    def test_with_medicines(self):
        from apps.health.models import Intake, IntakeSchedule, IntakeLog
        from apps.core.behavior.domain_medication import calculate_medicine_behavior_output

        med = Medicine.objects.create(
            user=self.user, name="Test Med", medicine_status="active",
            grace_period_minutes=30, start_date=date.today() - timedelta(days=30),
        )
        schedule = MedicineSchedule.objects.create(
            medicine=med, scheduled_time=time(8, 0),
            time_of_day="morning", days_of_week="0,1,2,3,4,5,6",
        )

        today = date.today()
        start = today - timedelta(days=6)

        # Log 5 taken, 1 late, 1 skipped over the 7-day window
        for i in range(5):
            MedicineLog.objects.create(
                user=self.user, medicine=med, schedule=schedule,
                scheduled_date=start + timedelta(days=i),
                log_status="taken",
            )
        MedicineLog.objects.create(
            user=self.user, medicine=med, schedule=schedule,
            scheduled_date=start + timedelta(days=5),
            log_status="late",
        )
        MedicineLog.objects.create(
            user=self.user, medicine=med, schedule=schedule,
            scheduled_date=start + timedelta(days=6),
            log_status="skipped",
        )

        result = calculate_medicine_behavior_output(self.user, start, today)
        self.assertIsNotNone(result)
        self.assertEqual(result['domain'], 'medication')
        self.assertEqual(result['completed'], 5)
        self.assertEqual(result['late'], 1)
        self.assertEqual(result['skipped'], 1)
        self.assertGreater(result['adherence'], 0)


class BehaviorScoreEngineTest(TestCase):
    """Tests for compute_behavior_score."""

    def test_no_domains_returns_none(self):
        from apps.users.models import User, TermsAcceptance
        user = User.objects.create_user(
            email='score_test@test.com', password='test123'
        )
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

        from apps.core.behavior.behavior_score_engine import compute_behavior_score
        today = date.today()
        result = compute_behavior_score(user, today - timedelta(days=7), today)
        self.assertIsNone(result['score'])
        self.assertGreater(len(result['domains_missing']), 0)

    @patch('apps.core.behavior.domain_medication.calculate_medicine_behavior_output')
    @patch('apps.core.behavior.domain_workout.calculate_workout_behavior_output')
    @patch('apps.core.behavior.domain_routine.calculate_routine_behavior_output')
    def test_composite_score(self, mock_routine, mock_workout, mock_med):
        from apps.users.models import User, TermsAcceptance
        user = User.objects.create_user(
            email='composite@test.com', password='test123'
        )
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

        mock_med.return_value = build_behavior_output(
            'medication', expected=14, completed=12, late=1, skipped=0, missed=1
        )
        mock_workout.return_value = build_behavior_output(
            'workout', expected=6, completed=5, late=1, skipped=0, missed=0
        )
        mock_routine.return_value = None  # no routines yet

        from apps.core.behavior.behavior_score_engine import compute_behavior_score
        today = date.today()
        result = compute_behavior_score(user, today - timedelta(days=7), today)

        self.assertIsNotNone(result['score'])
        self.assertEqual(len(result['domains']), 2)
        self.assertIn('routine', result['domains_missing'])
        self.assertIsNotNone(result['strongest_domain'])
        self.assertIsNotNone(result['weakest_domain'])
