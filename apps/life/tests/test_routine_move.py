"""
Tests for routine item move — write-time anchoring and immutability.

Covers:
  - routine_at_time is set at creation time on all paths
  - routine_at_time is immutable after creation (model-level guard)
  - move_routine_item() changes schedule.routine FK
  - historical logs retain original routine_at_time after move
  - execution truth uses write-time attribution for historical dates
  - get_log_routine / get_log_routine_name helpers
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.life.services.routine_helpers import (
    get_log_routine,
    get_log_routine_name,
    move_routine_item,
    skip_routine,
    toggle_routine_completion,
)
from apps.users.models import User, TermsAcceptance


class RoutineMoveTestMixin:
    """Shared setup for routine move tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='move@test.com', password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.timezone = 'America/Chicago'
        self.user.preferences.save()

        self.nightly = Routine.objects.create(
            user=self.user, name='Nightly', time_of_day='evening', is_active=True,
        )
        self.evening = Routine.objects.create(
            user=self.user, name='Evening', time_of_day='evening', is_active=True,
        )
        self.schedule = RoutineSchedule.objects.create(
            routine=self.nightly, name='Prayer Time',
            scheduled_time=time(21, 0),
            grace_period_minutes=30,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )


class TestRoutineAtTimeSetOnCreation(RoutineMoveTestMixin, TestCase):
    """routine_at_time must be set on every RoutineLog creation path."""

    def test_toggle_completion_sets_routine_at_time(self):
        today = date.today()
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)
        self.assertEqual(log.routine_at_time_id, self.nightly.id)

    def test_skip_sets_routine_at_time(self):
        today = date.today()
        skip_routine(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)
        self.assertEqual(log.routine_at_time_id, self.nightly.id)

    def test_skip_update_does_not_overwrite_routine_at_time(self):
        """When skip updates an existing log, routine_at_time stays unchanged."""
        today = date.today()
        # Create log via toggle first
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)
        self.assertEqual(log.routine_at_time_id, self.nightly.id)

        # Now move the schedule to Evening
        move_routine_item(self.user, self.schedule, self.evening)

        # Skip the same day — should NOT change routine_at_time
        skip_routine(self.user, self.schedule, today)
        log.refresh_from_db()
        # routine_at_time stays as Nightly (the routine at creation time)
        self.assertEqual(log.routine_at_time_id, self.nightly.id)

    def test_bulk_toggle_sets_routine_at_time(self):
        from apps.life.services.routine_helpers import toggle_routine_complete
        today = date.today()
        toggle_routine_complete(self.user, self.nightly, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)
        self.assertEqual(log.routine_at_time_id, self.nightly.id)


class TestRoutineAtTimeImmutability(RoutineMoveTestMixin, TestCase):
    """routine_at_time must never change after creation."""

    def test_save_rejects_routine_at_time_change(self):
        today = date.today()
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)

        log.routine_at_time = self.evening
        with self.assertRaises(ValueError) as ctx:
            log.save()
        self.assertIn('immutable', str(ctx.exception))

    def test_save_allows_setting_null_to_value(self):
        """Pre-migration logs (null) can be backfilled once."""
        today = date.today()
        log = RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=today,
            log_status='completed',
            completed_at=timezone.now(),
            # routine_at_time deliberately omitted (null)
        )
        self.assertIsNone(log.routine_at_time_id)

        # Setting from null → value is allowed (one-time backfill)
        log.routine_at_time = self.nightly
        log.save(update_fields=['routine_at_time'])
        log.refresh_from_db()
        self.assertEqual(log.routine_at_time_id, self.nightly.id)

    def test_save_allows_same_value(self):
        """Re-saving with the same routine_at_time doesn't raise."""
        today = date.today()
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)

        # Same value — no error
        log.routine_at_time = self.nightly
        log.save()  # Should not raise

    def test_update_fields_excluding_routine_at_time_is_safe(self):
        """Normal status updates (e.g., timing) don't trigger the guard."""
        today = date.today()
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)

        log.timing = 'late'
        log.save(update_fields=['timing', 'updated_at'])  # Should not raise


class TestMoveRoutineItem(RoutineMoveTestMixin, TestCase):
    """move_routine_item() service function."""

    def test_move_changes_routine_fk(self):
        result = move_routine_item(self.user, self.schedule, self.evening)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.routine_id, self.evening.id)
        self.assertTrue(result['success'])
        self.assertEqual(result['from_routine'], 'Nightly')
        self.assertEqual(result['to_routine'], 'Evening')

    def test_move_preserves_schedule_pk(self):
        original_pk = self.schedule.pk
        move_routine_item(self.user, self.schedule, self.evening)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.pk, original_pk)

    def test_historical_logs_retain_original_routine(self):
        """Logs created before move keep routine_at_time = source routine."""
        yesterday = date.today() - timedelta(days=1)
        RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=yesterday,
            log_status='completed',
            completed_at=timezone.now() - timedelta(days=1),
            routine_at_time=self.nightly,
        )

        # Move schedule
        move_routine_item(self.user, self.schedule, self.evening)

        # Historical log still points to Nightly
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=yesterday)
        self.assertEqual(log.routine_at_time_id, self.nightly.id)

    def test_new_log_after_move_uses_target_routine(self):
        """Logs created after move get routine_at_time = target routine."""
        move_routine_item(self.user, self.schedule, self.evening)

        today = date.today()
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=today)
        self.assertEqual(log.routine_at_time_id, self.evening.id)

    def test_move_rejects_same_routine(self):
        with self.assertRaises(ValueError):
            move_routine_item(self.user, self.schedule, self.nightly)

    def test_move_rejects_other_user(self):
        other_user = User.objects.create_user(
            email='other@test.com', password='testpass123',
        )
        other_routine = Routine.objects.create(
            user=other_user, name='Other', time_of_day='morning', is_active=True,
        )
        with self.assertRaises(ValueError):
            move_routine_item(self.user, self.schedule, other_routine)

    def test_move_rejects_deleted_target(self):
        self.evening.status = 'deleted'
        self.evening.save()
        with self.assertRaises(ValueError):
            move_routine_item(self.user, self.schedule, self.evening)

    def test_move_rejects_inactive_target(self):
        self.evening.is_active = False
        self.evening.save()
        with self.assertRaises(ValueError):
            move_routine_item(self.user, self.schedule, self.evening)


class TestGetLogRoutineHelpers(RoutineMoveTestMixin, TestCase):
    """get_log_routine / get_log_routine_name helpers."""

    def test_returns_routine_at_time_when_set(self):
        today = date.today()
        toggle_routine_completion(self.user, self.schedule, today)
        log = RoutineLog.objects.select_related(
            'routine_at_time', 'schedule__routine',
        ).get(schedule=self.schedule, scheduled_date=today)

        self.assertEqual(get_log_routine(log), self.nightly)
        self.assertEqual(get_log_routine_name(log), 'Nightly')

    def test_falls_back_to_schedule_routine_when_null(self):
        today = date.today()
        log = RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=today,
            log_status='completed',
            completed_at=timezone.now(),
            # routine_at_time deliberately null (pre-migration)
        )
        log = RoutineLog.objects.select_related(
            'routine_at_time', 'schedule__routine',
        ).get(pk=log.pk)

        self.assertEqual(get_log_routine(log), self.nightly)
        self.assertEqual(get_log_routine_name(log), 'Nightly')

    def test_after_move_historical_log_shows_original(self):
        yesterday = date.today() - timedelta(days=1)
        RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=yesterday,
            log_status='completed',
            completed_at=timezone.now() - timedelta(days=1),
            routine_at_time=self.nightly,
        )

        move_routine_item(self.user, self.schedule, self.evening)

        log = RoutineLog.objects.select_related(
            'routine_at_time', 'schedule__routine',
        ).get(schedule=self.schedule, scheduled_date=yesterday)

        # Helper returns Nightly (historical), NOT Evening (current)
        self.assertEqual(get_log_routine(log), self.nightly)
        self.assertEqual(get_log_routine_name(log), 'Nightly')


class TestExecutionTruthHistoricalAttribution(RoutineMoveTestMixin, TestCase):
    """Execution truth engine uses write-time routine_at_time for history."""

    def test_historical_routine_grouping_uses_routine_at_time(self):
        from apps.core.execution.execution_truth_engine import _check_routines

        # Use 5 days ago to ensure it's always in the past (not user's "today")
        past_date = date.today() - timedelta(days=5)

        # Create log under Nightly
        RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=past_date,
            log_status='completed',
            completed_at=timezone.now() - timedelta(days=5),
            routine_at_time=self.nightly,
        )

        # Move schedule to Evening
        move_routine_item(self.user, self.schedule, self.evening)

        # Check historical truth — should attribute to Nightly
        result = _check_routines(self.user, past_date)
        self.assertIn('Nightly', result['items'])
        self.assertEqual(result['items']['Nightly']['completed'], 1)
        # Evening should NOT appear for that past date
        self.assertNotIn('Evening', result['items'])
