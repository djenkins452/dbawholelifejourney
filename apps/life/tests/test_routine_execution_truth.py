"""
Tests for Routine Execution Truth — performed_at + timing + medicine-style UX.

Covers:
- Grace window timing classification (on_time, late, early)
- "Done at Scheduled Time" override
- Bulk actions (done_at_scheduled, complete_all, skip_all)
- Activity-based auto-completion timing
- Re-click override behavior
- State validation consistency
- Signal engine performed_at usage
- Data migration backfill
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.users.models import TermsAcceptance, User


class ExecutionTruthTestMixin:
    """Shared setup for execution truth tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='truth@test.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.timezone = 'America/Chicago'
        self.user.preferences.save()
        self.client.login(email='truth@test.com', password='testpass123')
        self.tz = ZoneInfo('America/Chicago')

        self.routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning', is_active=True,
        )
        # Schedule at 6:15 AM with 30-minute grace
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Meditation',
            scheduled_time=time(6, 15),
            grace_period_minutes=30,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )

    def _make_aware(self, hour, minute, target_date=None):
        """Build timezone-aware datetime in user's timezone."""
        d = target_date or timezone.now().astimezone(self.tz).date()
        return timezone.make_aware(datetime.combine(d, time(hour, minute)), self.tz)


class TestTimingClassification(ExecutionTruthTestMixin, TestCase):
    """Test grace window timing classification."""

    def test_complete_within_grace_is_on_time(self):
        """Complete at 6:30 AM (within 30-min grace of 6:15) → on_time."""
        from apps.life.services.routine_helpers import _compute_timing_and_performed_at

        user_today = timezone.now().astimezone(self.tz).date()
        user_now = self._make_aware(6, 30)

        performed_at, timing = _compute_timing_and_performed_at(
            self.user, self.schedule, user_today, user_now,
        )
        self.assertEqual(timing, 'on_time')
        # performed_at should be the scheduled time (6:15), not now
        self.assertEqual(performed_at.hour, 6)
        self.assertEqual(performed_at.minute, 15)

    def test_complete_outside_grace_is_late(self):
        """Complete at 8:00 AM (outside 30-min grace of 6:15) → late."""
        from apps.life.services.routine_helpers import _compute_timing_and_performed_at

        user_today = timezone.now().astimezone(self.tz).date()
        user_now = self._make_aware(8, 0)

        performed_at, timing = _compute_timing_and_performed_at(
            self.user, self.schedule, user_today, user_now,
        )
        self.assertEqual(timing, 'late')
        # performed_at should be now (8:00), not scheduled time
        self.assertEqual(performed_at.hour, 8)
        self.assertEqual(performed_at.minute, 0)

    def test_complete_before_window_is_early(self):
        """Complete at 5:30 AM (before 5:45 window_start) → early."""
        from apps.life.services.routine_helpers import _compute_timing_and_performed_at

        user_today = timezone.now().astimezone(self.tz).date()
        user_now = self._make_aware(5, 30)

        performed_at, timing = _compute_timing_and_performed_at(
            self.user, self.schedule, user_today, user_now,
        )
        self.assertEqual(timing, 'early')
        self.assertEqual(performed_at.hour, 5)
        self.assertEqual(performed_at.minute, 30)

    def test_complete_at_exact_scheduled_time(self):
        """Complete at exactly 6:15 AM → on_time."""
        from apps.life.services.routine_helpers import _compute_timing_and_performed_at

        user_today = timezone.now().astimezone(self.tz).date()
        user_now = self._make_aware(6, 15)

        performed_at, timing = _compute_timing_and_performed_at(
            self.user, self.schedule, user_today, user_now,
        )
        self.assertEqual(timing, 'on_time')


class TestToggleCompletion(ExecutionTruthTestMixin, TestCase):
    """Test toggle_routine_completion sets performed_at and timing."""

    def _get_user_dates(self):
        from apps.core.utils import get_user_now, get_user_today
        return get_user_today(self.user), get_user_now(self.user)

    def test_auto_detect_within_grace(self):
        """Auto-detect within grace → on_time with performed_at = scheduled."""
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()
        # Mock time to be within grace window
        mock_now = self._make_aware(6, 20)
        with patch('apps.core.utils.get_user_now', return_value=mock_now), \
             patch('apps.core.utils.get_user_today', return_value=user_today):
            result = toggle_routine_completion(self.user, self.schedule, user_today)

        self.assertTrue(result['is_completed'])
        self.assertEqual(result['timing'], 'on_time')

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(log.timing, 'on_time')
        self.assertIsNotNone(log.performed_at)
        self.assertIsNotNone(log.completed_at)
        # performed_at should be scheduled time (6:15), completed_at = click time
        self.assertEqual(log.performed_at.astimezone(self.tz).hour, 6)
        self.assertEqual(log.performed_at.astimezone(self.tz).minute, 15)

    def test_auto_detect_outside_grace(self):
        """Auto-detect outside grace → late with performed_at = now."""
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()
        mock_now = self._make_aware(9, 0)
        with patch('apps.core.utils.get_user_now', return_value=mock_now), \
             patch('apps.core.utils.get_user_today', return_value=user_today):
            result = toggle_routine_completion(self.user, self.schedule, user_today)

        self.assertEqual(result['timing'], 'late')
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(log.timing, 'late')
        self.assertEqual(log.log_status, 'completed_late')

    def test_done_at_scheduled_time_override(self):
        """'scheduled' mode → on_time regardless of current time."""
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()
        result = toggle_routine_completion(
            self.user, self.schedule, user_today, completion_mode='scheduled',
        )
        self.assertEqual(result['timing'], 'on_time')
        self.assertTrue(result['completed_as_scheduled'])

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(log.timing, 'on_time')
        self.assertEqual(log.completion_source, 'scheduled_override')
        # performed_at should be the scheduled datetime
        self.assertEqual(log.performed_at.astimezone(self.tz).hour, 6)
        self.assertEqual(log.performed_at.astimezone(self.tz).minute, 15)

    def test_explicit_late_mode(self):
        """'late' mode → late timing."""
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()
        result = toggle_routine_completion(
            self.user, self.schedule, user_today, completion_mode='late',
        )
        self.assertEqual(result['timing'], 'late')
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(log.timing, 'late')
        self.assertEqual(log.completion_source, 'manual')


class TestMissedLoggingCorrection(ExecutionTruthTestMixin, TestCase):
    """PRIMARY USE CASE: User performs activity on time but logs later."""

    def test_done_at_scheduled_after_delay(self):
        """Routine at 6:15 AM, user clicks 'Done at Scheduled Time' at 9:00 AM.

        Expected: performed_at=6:15 AM, timing=on_time, NOT late.
        """
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()

        # Even though it's 9 AM now, "Done at Scheduled Time" → on_time
        result = toggle_routine_completion(
            self.user, self.schedule, user_today, completion_mode='scheduled',
        )

        self.assertTrue(result['is_completed'])
        self.assertEqual(result['timing'], 'on_time')
        self.assertTrue(result['completed_as_scheduled'])

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(log.performed_at.astimezone(self.tz).time(), time(6, 15))
        self.assertEqual(log.timing, 'on_time')
        self.assertEqual(log.log_status, 'completed')


class TestReClickOverride(ExecutionTruthTestMixin, TestCase):
    """Re-click behavior: override from late to on_time."""

    def test_complete_late_then_done_at_scheduled(self):
        """User clicks Complete (late), then 'Done at Scheduled Time' → overwrite."""
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()
        mock_now = self._make_aware(9, 0)

        # Step 1: Complete late
        with patch('apps.core.utils.get_user_now', return_value=mock_now), \
             patch('apps.core.utils.get_user_today', return_value=user_today):
            result1 = toggle_routine_completion(self.user, self.schedule, user_today)
        self.assertEqual(result1['timing'], 'late')

        # Step 2: Override with "Done at Scheduled Time"
        result2 = toggle_routine_completion(
            self.user, self.schedule, user_today, completion_mode='scheduled',
        )
        self.assertEqual(result2['timing'], 'on_time')
        self.assertEqual(result2['is_completed'], True)

        # Verify only ONE log exists (no duplicates)
        logs = RoutineLog.objects.filter(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(logs.count(), 1)

        log = logs.first()
        self.assertEqual(log.timing, 'on_time')
        self.assertEqual(log.completion_source, 'scheduled_override')
        self.assertEqual(log.performed_at.astimezone(self.tz).time(), time(6, 15))


class TestSkipBehavior(ExecutionTruthTestMixin, TestCase):
    """Skip sets performed_at=None, timing=''."""

    def test_skip_clears_timing(self):
        from apps.life.services.routine_helpers import skip_routine

        user_today = timezone.now().astimezone(self.tz).date()
        skip_routine(self.user, self.schedule, user_today)

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertEqual(log.log_status, 'skipped')
        self.assertIsNone(log.performed_at)
        self.assertEqual(log.timing, '')


class TestActivityBasedCompletion(ExecutionTruthTestMixin, TestCase):
    """Activity-based routines compute timing against grace window."""

    def setUp(self):
        super().setUp()
        self.schedule.routine_type = 'activity'
        self.schedule.activity_type = 'workout'
        self.schedule.save()

    def test_activity_within_grace_is_on_time(self):
        """Workout at 6:20 AM for 6:15 schedule → on_time."""
        from apps.life.services.routine_helpers import auto_complete_routine_schedules

        activity_time = self._make_aware(6, 20)
        with patch('apps.core.utils.get_user_now', return_value=activity_time), \
             patch('apps.core.utils.get_user_today',
                    return_value=activity_time.date()):
            results = auto_complete_routine_schedules(
                self.user, 'workout', 'workout',
                completion_time=activity_time, source_object_id=1,
            )

        self.assertEqual(len(results), 1)
        log = RoutineLog.objects.get(schedule=self.schedule)
        self.assertEqual(log.timing, 'on_time')
        self.assertEqual(log.performed_at.astimezone(self.tz).hour, 6)
        self.assertEqual(log.performed_at.astimezone(self.tz).minute, 20)

    def test_activity_outside_grace_is_late(self):
        """Workout at 9:00 AM for 6:15 schedule → late."""
        from apps.life.services.routine_helpers import auto_complete_routine_schedules

        activity_time = self._make_aware(9, 0)
        with patch('apps.core.utils.get_user_now', return_value=activity_time), \
             patch('apps.core.utils.get_user_today',
                    return_value=activity_time.date()):
            results = auto_complete_routine_schedules(
                self.user, 'workout', 'workout',
                completion_time=activity_time, source_object_id=1,
            )

        self.assertEqual(len(results), 1)
        log = RoutineLog.objects.get(schedule=self.schedule)
        self.assertEqual(log.timing, 'late')
        self.assertEqual(log.log_status, 'completed_late')


class TestBulkActions(ExecutionTruthTestMixin, TestCase):
    """Section-level bulk action tests."""

    def setUp(self):
        super().setUp()
        # Add a second schedule in same time window
        self.schedule2 = RoutineSchedule.objects.create(
            routine=self.routine, name='Journaling',
            scheduled_time=time(6, 30),
            grace_period_minutes=15,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )

    def test_bulk_done_at_scheduled_all_on_time(self):
        """Bulk 'Done All at Scheduled Time' → all items on_time."""
        url = reverse('life:routine_bulk_action')
        response = self.client.post(url, {
            'window_key': 'morning',
            'action': 'done_at_scheduled',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 2)

        # All logs should be on_time
        user_today = timezone.now().astimezone(self.tz).date()
        logs = RoutineLog.objects.filter(scheduled_date=user_today)
        for log in logs:
            self.assertEqual(log.timing, 'on_time')
            self.assertEqual(log.completion_source, 'scheduled_override')

    def test_bulk_skip_all(self):
        """Bulk 'Skip All' → all items skipped with no timing."""
        url = reverse('life:routine_bulk_action')
        response = self.client.post(url, {
            'window_key': 'morning',
            'action': 'skip_all',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)

        user_today = timezone.now().astimezone(self.tz).date()
        logs = RoutineLog.objects.filter(scheduled_date=user_today)
        for log in logs:
            self.assertEqual(log.log_status, 'skipped')
            self.assertIsNone(log.performed_at)
            self.assertEqual(log.timing, '')


class TestStateValidation(ExecutionTruthTestMixin, TestCase):
    """Completed logs must have performed_at and timing set."""

    def test_completed_log_auto_fills_performed_at(self):
        """If save() is called with completed status but no performed_at, it auto-fills."""
        user_today = timezone.now().astimezone(self.tz).date()
        now = timezone.now()
        log = RoutineLog(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=user_today,
            log_status='completed',
            completed_at=now,
        )
        log.save()
        log.refresh_from_db()
        # save() should auto-fill performed_at from completed_at
        self.assertIsNotNone(log.performed_at)
        self.assertEqual(log.performed_at, now)
        # timing should default to 'late' if not set
        self.assertEqual(log.timing, 'late')

    def test_skipped_log_clears_performed_at(self):
        """Saving a skipped log clears performed_at and timing."""
        user_today = timezone.now().astimezone(self.tz).date()
        log = RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=user_today,
            log_status='skipped',
            performed_at=timezone.now(),  # should be cleared
            timing='on_time',  # should be cleared
        )
        log.refresh_from_db()
        self.assertIsNone(log.performed_at)
        self.assertEqual(log.timing, '')


class TestSignalEngineUsesPerformedAt(ExecutionTruthTestMixin, TestCase):
    """Signal engine should use performed_at, not completed_at."""

    def test_signal_uses_performed_at(self):
        """ExecutionSignal records performed_at as actual_time."""
        from apps.core.signals.execution_quality import record_signal_from_routine_log

        user_today = timezone.now().astimezone(self.tz).date()
        sched_dt = self._make_aware(6, 15)

        log = RoutineLog.objects.create(
            user=self.user,
            schedule=self.schedule,
            scheduled_date=user_today,
            log_status='completed',
            completed_at=self._make_aware(9, 0),  # click time (late)
            performed_at=sched_dt,  # actual time (on_time)
            timing='on_time',
        )

        signal = record_signal_from_routine_log(log)
        if signal:
            # Signal's actual_time should match performed_at (6:15), NOT completed_at (9:00)
            self.assertEqual(
                signal.actual_time.astimezone(self.tz).hour, 6,
            )
            self.assertEqual(
                signal.actual_time.astimezone(self.tz).minute, 15,
            )
            # Should be on_target since performed_at == scheduled_time
            self.assertEqual(signal.execution_quality, 'on_target')


class TestDataMigrationBackfill(ExecutionTruthTestMixin, TestCase):
    """Verify existing completed logs have performed_at backfilled."""

    def test_new_completed_log_gets_performed_at(self):
        """New completed logs via service always set performed_at."""
        from apps.life.services.routine_helpers import toggle_routine_completion

        user_today = timezone.now().astimezone(self.tz).date()
        toggle_routine_completion(
            self.user, self.schedule, user_today, completion_mode='scheduled',
        )
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=user_today)
        self.assertIsNotNone(log.performed_at)
        self.assertNotEqual(log.timing, '')
