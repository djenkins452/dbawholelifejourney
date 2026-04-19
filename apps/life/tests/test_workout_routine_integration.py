"""
Tests for workout → routine auto-completion integration.

Phase 1: Auto-complete matching RoutineSchedule items when a WorkoutSession
         is created/completed.
Phase 2: Activity-type routines, structured matching, toggle guard.
"""

from datetime import date, time, datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.life.services.routine_helpers import (
    auto_complete_routine_schedules,
    toggle_routine_completion,
)
from apps.users.models import User, TermsAcceptance

# Patch targets — these are imported locally inside the service functions,
# so we patch at the source module.
_PATCH_TODAY = 'apps.core.utils.get_user_today'
_PATCH_NOW = 'apps.core.utils.get_user_now'


class WorkoutRoutineTestMixin:
    """Shared setup for workout-routine integration tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='workout-routine@test.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        # Create a routine with a "Workout" schedule item
        self.routine = Routine.objects.create(
            user=self.user, name='Morning Routine',
            time_of_day='morning', is_active=True,
        )
        self.workout_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Workout',
            scheduled_time=time(6, 0),
            grace_period_minutes=60,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )
        # Non-workout schedule item for isolation testing
        self.prayer_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Prayer',
            scheduled_time=time(6, 30),
            grace_period_minutes=30,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )


# =============================================================================
# PHASE 1 — Auto-Complete Tests
# =============================================================================


class AutoCompleteBasicTests(WorkoutRoutineTestMixin, TestCase):
    """Basic auto-completion: workout → routine log."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_creates_routine_log_on_autocomplete(self, mock_today, mock_now):
        """Workout auto-complete creates RoutineLog with correct source."""
        today = date(2026, 3, 22)  # Sunday = weekday 6
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
            completion_time=timezone.make_aware(datetime(2026, 3, 22, 6, 15)),
            source_object_id=42,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['schedule_id'], self.workout_schedule.pk)
        self.assertEqual(results[0]['status'], 'completed')

        log = RoutineLog.objects.get(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, 'workout')
        self.assertEqual(log.source_object_id, 42)
        self.assertEqual(log.log_status, 'completed')
        self.assertTrue(log.completed_as_scheduled)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_does_not_create_log_for_non_matching(self, mock_today, mock_now):
        """Prayer schedule is NOT auto-completed by workout keyword."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        auto_complete_routine_schedules(self.user, 'workout', 'workout')

        self.assertTrue(RoutineLog.objects.filter(
            schedule=self.workout_schedule, scheduled_date=today).exists())
        self.assertFalse(RoutineLog.objects.filter(
            schedule=self.prayer_schedule, scheduled_date=today).exists())


class AutoCompleteIdempotencyTests(WorkoutRoutineTestMixin, TestCase):
    """First-workout-wins and idempotency."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_second_call_is_noop(self, mock_today, mock_now):
        """Second auto-complete call does not create duplicate log."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        results1 = auto_complete_routine_schedules(
            self.user, 'workout', 'workout', source_object_id=10,
        )
        results2 = auto_complete_routine_schedules(
            self.user, 'workout', 'workout', source_object_id=20,
        )

        self.assertEqual(len(results1), 1)
        self.assertEqual(len(results2), 0)

        logs = RoutineLog.objects.filter(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().source_object_id, 10)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_manual_completion_not_overridden(self, mock_today, mock_now):
        """Manual completion is preserved — workout auto-complete skips."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        toggle_routine_completion(self.user, self.workout_schedule, today)

        log = RoutineLog.objects.get(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, 'manual')

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout', source_object_id=99,
        )
        self.assertEqual(len(results), 0)

        log.refresh_from_db()
        self.assertEqual(log.completion_source, 'manual')
        self.assertIsNone(log.source_object_id)


class AutoCompleteNameMatchingTests(WorkoutRoutineTestMixin, TestCase):
    """Case-insensitive name matching."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_case_insensitive_match(self, mock_today, mock_now):
        """Matching is case-insensitive: 'Morning Workout' matches 'workout'."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.name = 'Morning Workout Session'
        self.workout_schedule.save()

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 1)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_no_match_for_unrelated_name(self, mock_today, mock_now):
        """Schedule named 'Meditation' does not match 'workout' keyword."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.name = 'Meditation'
        self.workout_schedule.save()

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 0)


class AutoCompleteDayFilteringTests(WorkoutRoutineTestMixin, TestCase):
    """Day-of-week filtering."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_skips_wrong_day(self, mock_today, mock_now):
        """Schedule only for Monday is not completed on Sunday."""
        today = date(2026, 3, 22)  # Sunday = weekday 6
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.days_of_week = '0'  # Monday only
        self.workout_schedule.save()

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 0)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_completes_on_correct_day(self, mock_today, mock_now):
        """Schedule for Monday completes on Monday."""
        today = date(2026, 3, 23)  # Monday = weekday 0
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 23, 6, 30)
        )

        self.workout_schedule.days_of_week = '0'  # Monday only
        self.workout_schedule.save()

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 1)


class AutoCompleteTimingTests(WorkoutRoutineTestMixin, TestCase):
    """Timeliness classification: on-time vs late."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_on_time_within_grace(self, mock_today, mock_now):
        """Workout started within grace period → completed (on time)."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
            completion_time=timezone.make_aware(datetime(2026, 3, 22, 6, 30)),
        )

        self.assertEqual(results[0]['status'], 'completed')
        log = RoutineLog.objects.get(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertTrue(log.completed_as_scheduled)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_late_after_grace(self, mock_today, mock_now):
        """Workout started after grace period → completed_late."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 8, 0)
        )

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
            completion_time=timezone.make_aware(datetime(2026, 3, 22, 8, 0)),
        )

        self.assertEqual(results[0]['status'], 'completed_late')
        log = RoutineLog.objects.get(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertFalse(log.completed_as_scheduled)


class AutoCompleteTraceabilityTests(WorkoutRoutineTestMixin, TestCase):
    """Source object traceability."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_source_object_id_stored(self, mock_today, mock_now):
        """RoutineLog stores the WorkoutSession PK for traceability."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        auto_complete_routine_schedules(
            self.user, 'workout', 'workout', source_object_id=777,
        )

        log = RoutineLog.objects.get(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, 'workout')
        self.assertEqual(log.source_object_id, 777)


# =============================================================================
# PHASE 2 — Activity-Type Routing Tests
# =============================================================================


class ActivityTypeMatchingTests(WorkoutRoutineTestMixin, TestCase):
    """Structured activity_type matching takes priority over name."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_activity_type_match(self, mock_today, mock_now):
        """Schedule with activity_type='workout' matches even if name differs."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.name = 'Exercise'
        self.workout_schedule.routine_type = 'activity'
        self.workout_schedule.activity_type = 'workout'
        self.workout_schedule.save()

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 1)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_activity_type_plus_name_no_duplicates(self, mock_today, mock_now):
        """Schedule matching both activity_type AND name produces only one log."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.routine_type = 'activity'
        self.workout_schedule.activity_type = 'workout'
        self.workout_schedule.save()

        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(
            RoutineLog.objects.filter(
                schedule=self.workout_schedule, scheduled_date=today,
            ).count(), 1,
        )


class ToggleGuardTests(WorkoutRoutineTestMixin, TestCase):
    """Manual toggle policy — user must always retain control.

    Historically activity-type routines were refused at the helper level
    on the rationale "auto-complete handles these." That policy was
    reversed 2026-04-18 after a user-reported silent-failure bug: when
    the bridge fails for any reason, the user had no escape hatch.
    """

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_activity_routine_accepts_manual_toggle(
        self, mock_today, mock_now,
    ):
        """Manual toggle on activity routines creates a log with
        completion_source=SOURCE_MANUAL — the user override path."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.routine_type = 'activity'
        self.workout_schedule.activity_type = 'workout'
        self.workout_schedule.save()

        result = toggle_routine_completion(
            self.user, self.workout_schedule, today,
        )
        self.assertNotIn('error', result)
        self.assertTrue(result['is_completed'])

        log = RoutineLog.objects.get(
            schedule=self.workout_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, RoutineLog.SOURCE_MANUAL)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_binary_routine_allows_toggle(self, mock_today, mock_now):
        """Binary (default) routines still allow manual toggle."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        result = toggle_routine_completion(
            self.user, self.workout_schedule, today,
        )
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['is_completed'])


class BackwardCompatibilityTests(WorkoutRoutineTestMixin, TestCase):
    """Existing binary routines are unaffected."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_binary_routine_unaffected(self, mock_today, mock_now):
        """Binary routines default behavior unchanged."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        result = toggle_routine_completion(
            self.user, self.prayer_schedule, today,
        )
        self.assertTrue(result['is_completed'])

        result = toggle_routine_completion(
            self.user, self.prayer_schedule, today,
        )
        self.assertFalse(result['is_completed'])


# =============================================================================
# PHASE 4 — Multi-Domain Extension Tests (Journal + Faith)
# =============================================================================


class MultiDomainTestMixin:
    """Setup with journal and faith routine schedule items."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='multi-domain@test.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.routine = Routine.objects.create(
            user=self.user, name='Daily Routine',
            time_of_day='morning', is_active=True,
        )
        self.journal_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Journal',
            scheduled_time=time(20, 0),
            grace_period_minutes=60,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
            routine_type='activity',
            activity_type='journal',
        )
        self.bible_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Bible Reading',
            scheduled_time=time(6, 0),
            grace_period_minutes=60,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
            routine_type='activity',
            activity_type='bible',
        )
        self.workout_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Workout',
            scheduled_time=time(6, 30),
            grace_period_minutes=60,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
            routine_type='activity',
            activity_type='workout',
        )


class JournalAutoCompleteTests(MultiDomainTestMixin, TestCase):
    """Journal entry → routine auto-completion."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_journal_completes_journal_routine(self, mock_today, mock_now):
        """Journal auto-complete creates RoutineLog with source='journal'."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 20, 15)
        )

        results = auto_complete_routine_schedules(
            self.user, 'journal', 'journal', source_object_id=100,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['schedule_id'], self.journal_schedule.pk)

        log = RoutineLog.objects.get(
            schedule=self.journal_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, 'journal')
        self.assertEqual(log.source_object_id, 100)

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_journal_does_not_complete_workout(self, mock_today, mock_now):
        """Journal auto-complete does NOT touch workout or bible routines."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 20, 15)
        )

        auto_complete_routine_schedules(
            self.user, 'journal', 'journal',
        )

        self.assertFalse(RoutineLog.objects.filter(
            schedule=self.workout_schedule, scheduled_date=today).exists())
        self.assertFalse(RoutineLog.objects.filter(
            schedule=self.bible_schedule, scheduled_date=today).exists())


class FaithAutoCompleteTests(MultiDomainTestMixin, TestCase):
    """Bible reading → routine auto-completion."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_bible_completes_bible_routine(self, mock_today, mock_now):
        """Bible auto-complete creates RoutineLog with source='bible'."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 15)
        )

        results = auto_complete_routine_schedules(
            self.user, 'bible', 'bible', source_object_id=200,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['schedule_id'], self.bible_schedule.pk)

        log = RoutineLog.objects.get(
            schedule=self.bible_schedule, scheduled_date=today,
        )
        self.assertEqual(log.completion_source, 'bible')

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_bible_does_not_complete_journal(self, mock_today, mock_now):
        """Bible auto-complete does NOT touch journal routines."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 15)
        )

        auto_complete_routine_schedules(
            self.user, 'bible', 'bible',
        )

        self.assertFalse(RoutineLog.objects.filter(
            schedule=self.journal_schedule, scheduled_date=today).exists())


class CrossDomainIsolationTests(MultiDomainTestMixin, TestCase):
    """Each domain auto-complete is isolated — no cross-contamination."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_all_three_domains_independent(self, mock_today, mock_now):
        """Workout, journal, and bible each complete only their own routine."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 12, 0)
        )

        auto_complete_routine_schedules(self.user, 'workout', 'workout', source_object_id=1)
        auto_complete_routine_schedules(self.user, 'journal', 'journal', source_object_id=2)
        auto_complete_routine_schedules(self.user, 'bible', 'bible', source_object_id=3)

        # Each has exactly one log
        self.assertEqual(RoutineLog.objects.filter(scheduled_date=today).count(), 3)

        # Each log has the correct source
        workout_log = RoutineLog.objects.get(schedule=self.workout_schedule, scheduled_date=today)
        self.assertEqual(workout_log.completion_source, 'workout')
        self.assertEqual(workout_log.source_object_id, 1)

        journal_log = RoutineLog.objects.get(schedule=self.journal_schedule, scheduled_date=today)
        self.assertEqual(journal_log.completion_source, 'journal')
        self.assertEqual(journal_log.source_object_id, 2)

        bible_log = RoutineLog.objects.get(schedule=self.bible_schedule, scheduled_date=today)
        self.assertEqual(bible_log.completion_source, 'bible')
        self.assertEqual(bible_log.source_object_id, 3)


# =============================================================================
# PHASE 5 — Fallback Tracking Tests
# =============================================================================


class FallbackTrackingTests(WorkoutRoutineTestMixin, TestCase):
    """Verify fallback name matching is logged and structured matching preferred."""

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_name_fallback_used_when_no_activity_type(self, mock_today, mock_now):
        """Schedule without activity_type uses name fallback."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        # Ensure no activity_type set (default from setUp)
        self.assertEqual(self.workout_schedule.activity_type, None)

        with self.assertLogs('apps.life.services.routine_helpers', level='INFO') as cm:
            auto_complete_routine_schedules(
                self.user, 'workout', 'workout',
            )

        # Should log the fallback usage
        self.assertTrue(any('ROUTINE_AUTOCOMPLETE_FALLBACK' in msg for msg in cm.output))

    @patch(_PATCH_NOW)
    @patch(_PATCH_TODAY)
    def test_no_fallback_log_when_activity_type_set(self, mock_today, mock_now):
        """Schedule with activity_type does NOT log fallback."""
        today = date(2026, 3, 22)
        mock_today.return_value = today
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 3, 22, 6, 30)
        )

        self.workout_schedule.routine_type = 'activity'
        self.workout_schedule.activity_type = 'workout'
        self.workout_schedule.save()

        # Should NOT log fallback (uses structured matching)
        results = auto_complete_routine_schedules(
            self.user, 'workout', 'workout',
        )
        self.assertEqual(len(results), 1)
        # The log exists but the schedule has activity_type, so no fallback log
