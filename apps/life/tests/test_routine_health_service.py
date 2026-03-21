"""
Tests for Routine Health & Drift Signal Service.
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase

from apps.users.models import User, TermsAcceptance


def _create_test_user(email='health@test.com'):
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class MaintenanceOverdueTest(TestCase):
    """Detect overdue maintenance based on follow_up_days."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user()
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            follow_up_days=90,
            last_maintenance_date=date.today() - timedelta(days=100),
        )

    def test_overdue_detected(self):
        from apps.life.services.routine_health_service import evaluate_routine_health
        signals = evaluate_routine_health(self.schedule, date.today())
        overdue = [s for s in signals if s['type'] == 'maintenance_overdue']
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]['days'], 10)
        self.assertIn('overdue', overdue[0]['detail'])

    def test_not_overdue_when_recent(self):
        from apps.life.services.routine_health_service import evaluate_routine_health
        self.schedule.last_maintenance_date = date.today() - timedelta(days=30)
        self.schedule.save()
        signals = evaluate_routine_health(self.schedule, date.today())
        overdue = [s for s in signals if s['type'] == 'maintenance_overdue']
        self.assertEqual(len(overdue), 0)

    def test_no_overdue_without_follow_up_days(self):
        from apps.life.services.routine_health_service import evaluate_routine_health
        self.schedule.follow_up_days = None
        self.schedule.save()
        signals = evaluate_routine_health(self.schedule, date.today())
        overdue = [s for s in signals if s['type'] == 'maintenance_overdue']
        self.assertEqual(len(overdue), 0)


class DriftDetectionTest(TestCase):
    """Detect completion drift from late/skipped patterns."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user('drift@test.com')
        self.routine = Routine.objects.create(user=self.user, name='Morning')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Prayer',
            scheduled_time=time(6, 0),
        )

    def test_drift_detected_with_late_pattern(self):
        from apps.life.models import RoutineLog
        from apps.life.services.routine_health_service import evaluate_routine_health
        today = date.today()
        # Create 5 logs: 4 completed_late, 1 completed
        for i in range(5):
            RoutineLog.objects.create(
                user=self.user, schedule=self.schedule,
                scheduled_date=today - timedelta(days=i),
                log_status='completed_late' if i < 4 else 'completed',
            )
        signals = evaluate_routine_health(self.schedule, today)
        drift = [s for s in signals if s['type'] == 'drift']
        self.assertEqual(len(drift), 1)

    def test_no_drift_when_consistent(self):
        from apps.life.models import RoutineLog
        from apps.life.services.routine_health_service import evaluate_routine_health
        today = date.today()
        for i in range(5):
            RoutineLog.objects.create(
                user=self.user, schedule=self.schedule,
                scheduled_date=today - timedelta(days=i),
                log_status='completed',
            )
        signals = evaluate_routine_health(self.schedule, today)
        drift = [s for s in signals if s['type'] == 'drift']
        self.assertEqual(len(drift), 0)

    def test_no_drift_with_insufficient_data(self):
        from apps.life.models import RoutineLog
        from apps.life.services.routine_health_service import evaluate_routine_health
        today = date.today()
        # Only 2 logs — not enough data
        for i in range(2):
            RoutineLog.objects.create(
                user=self.user, schedule=self.schedule,
                scheduled_date=today - timedelta(days=i),
                log_status='skipped',
            )
        signals = evaluate_routine_health(self.schedule, today)
        drift = [s for s in signals if s['type'] == 'drift']
        self.assertEqual(len(drift), 0)


class OverMaintenanceTest(TestCase):
    """Detect maintenance happening too frequently."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user('over@test.com')
        self.routine = Routine.objects.create(user=self.user, name='Vehicle')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Oil Change',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            follow_up_days=90,
        )

    def test_over_maintenance_detected(self):
        from apps.life.models import MaintenanceLog
        from apps.life.services.routine_health_service import evaluate_routine_health
        today = date.today()
        # Two maintenance logs in 30 days (expected interval: 90)
        MaintenanceLog.objects.create(
            user=self.user, title='Oil Change 1', date=today - timedelta(days=10),
            matched_schedule_id=self.schedule.pk,
        )
        MaintenanceLog.objects.create(
            user=self.user, title='Oil Change 2', date=today - timedelta(days=5),
            matched_schedule_id=self.schedule.pk,
        )
        signals = evaluate_routine_health(self.schedule, today)
        over = [s for s in signals if s['type'] == 'over_maintenance']
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0]['severity'], 'low')


class NeglectDetectionTest(TestCase):
    """Detect long periods with no activity."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = _create_test_user('neglect@test.com')
        self.routine = Routine.objects.create(user=self.user, name='Home')
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='HVAC Filter',
            scheduled_time=time(9, 0),
            creates_maintenance_log=True,
            follow_up_days=90,
        )

    def test_neglect_detected_with_no_activity(self):
        from apps.life.services.routine_health_service import evaluate_routine_health
        signals = evaluate_routine_health(self.schedule, date.today())
        neglect = [s for s in signals if s['type'] == 'neglect']
        self.assertEqual(len(neglect), 1)
        self.assertEqual(neglect[0]['severity'], 'high')

    def test_no_neglect_with_recent_maintenance(self):
        from apps.life.services.routine_health_service import evaluate_routine_health
        self.schedule.last_maintenance_date = date.today() - timedelta(days=30)
        self.schedule.save()
        signals = evaluate_routine_health(self.schedule, date.today())
        neglect = [s for s in signals if s['type'] == 'neglect']
        self.assertEqual(len(neglect), 0)


class HealthyRoutineTest(TestCase):
    """Verify no signals for healthy routines."""

    def test_no_signals_for_healthy_routine(self):
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        from apps.life.services.routine_health_service import evaluate_routine_health
        user = _create_test_user('healthy@test.com')
        routine = Routine.objects.create(user=user, name='Morning')
        schedule = RoutineSchedule.objects.create(
            routine=routine, name='Prayer',
            scheduled_time=time(6, 0),
        )
        today = date.today()
        for i in range(5):
            RoutineLog.objects.create(
                user=user, schedule=schedule,
                scheduled_date=today - timedelta(days=i),
                log_status='completed',
            )
        signals = evaluate_routine_health(schedule, today)
        self.assertEqual(len(signals), 0)


class EvaluateAllTest(TestCase):
    """Test the batch evaluation function."""

    def test_evaluate_all_returns_only_signaled(self):
        from apps.life.models import Routine, RoutineSchedule
        from apps.life.services.routine_health_service import evaluate_all_routine_health
        user = _create_test_user('all@test.com')
        routine = Routine.objects.create(user=user, name='Test')
        # Healthy schedule — no signals expected
        RoutineSchedule.objects.create(
            routine=routine, name='Healthy Item',
            scheduled_time=time(9, 0),
        )
        # Neglected schedule — signals expected
        RoutineSchedule.objects.create(
            routine=routine, name='Neglected',
            scheduled_time=time(10, 0),
            creates_maintenance_log=True,
            follow_up_days=30,
        )
        results = evaluate_all_routine_health(user)
        # Only the neglected one should appear
        names = [r['schedule_name'] for r in results]
        self.assertIn('Neglected', names)
        self.assertNotIn('Healthy Item', names)
