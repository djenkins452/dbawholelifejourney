"""Regression test: activity-type routines must remain manually toggleable.

Previously, `toggle_routine_completion` (apps/life/services/routine_helpers.py)
returned an early error-dict for any RoutineSchedule with
`routine_type='activity'`, on the rationale that activity routines are
auto-completed by their data source (e.g., WorkoutSession). In practice
this meant: if the auto-complete bridge failed for any reason — bridge
code bug, integration timing, sync lag — the user had no way to mark
the routine complete on the dashboard. The checkbox click POSTed, the
helper refused, the view ignored the error, and the page re-rendered
unchanged with no feedback.

The user must always retain manual control. This test locks that in.
"""

from datetime import time

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.life.services.routine_helpers import toggle_routine_completion
from apps.users.models import TermsAcceptance, User


class ActivityRoutineManualToggleTests(TestCase):
    """Activity routines must accept manual toggle in both directions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="activity-toggle@test.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.routine = Routine.objects.create(
            user=self.user, name="Morning Routine",
            time_of_day="morning", is_active=True,
        )
        # Activity-type — the exact case that was broken.
        self.activity_schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Workout",
            routine_type=RoutineSchedule.ROUTINE_TYPE_ACTIVITY,
            activity_type=RoutineSchedule.ACTIVITY_TYPE_WORKOUT,
            scheduled_time=time(6, 0),
            grace_period_minutes=60,
            days_of_week="0,1,2,3,4,5,6",
            is_active=True,
        )
        self.today = timezone.localdate()

    def test_manual_toggle_creates_routinelog_with_manual_source(self):
        """Clicking the checkbox on an activity routine creates a log
        with completion_source=SOURCE_MANUAL — distinguishable from a
        bridged auto-complete which would set SOURCE_WORKOUT."""
        result = toggle_routine_completion(
            self.user, self.activity_schedule, self.today,
        )

        self.assertTrue(
            result.get('is_completed'),
            f"Expected is_completed=True; got result={result}",
        )
        self.assertNotIn(
            'error', result,
            f"Manual toggle on activity routine returned an error: {result}",
        )

        log = RoutineLog.objects.get(
            user=self.user,
            schedule=self.activity_schedule,
            scheduled_date=self.today,
        )
        self.assertIn(log.log_status, ('completed', 'completed_late'))
        self.assertEqual(
            log.completion_source, RoutineLog.SOURCE_MANUAL,
            "Manually-toggled activity routine must record "
            "completion_source=SOURCE_MANUAL so reports can distinguish "
            "manual overrides from successful auto-bridges",
        )

    def test_manual_toggle_off_removes_routinelog(self):
        """Second click on a completed activity routine removes the log."""
        # First click: check it.
        toggle_routine_completion(
            self.user, self.activity_schedule, self.today,
        )
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=self.activity_schedule,
                scheduled_date=self.today,
            ).exists()
        )

        # Second click: uncheck.
        result = toggle_routine_completion(
            self.user, self.activity_schedule, self.today,
        )

        self.assertFalse(result.get('is_completed'))
        self.assertFalse(
            RoutineLog.objects.filter(
                schedule=self.activity_schedule,
                scheduled_date=self.today,
            ).exists(),
            "Toggling off a manually-completed activity routine must "
            "delete the RoutineLog, same as a binary routine",
        )

    def test_manual_override_survives_auto_bridge_failure(self):
        """End-to-end scenario from the user report:
        auto-bridge silently failed to create a log, user clicks to
        override — the manual log must stick even though a future
        auto-bridge attempt could run."""
        # No log exists (auto-bridge never fired).
        self.assertFalse(
            RoutineLog.objects.filter(
                schedule=self.activity_schedule,
                scheduled_date=self.today,
            ).exists()
        )

        # User clicks manually.
        toggle_routine_completion(
            self.user, self.activity_schedule, self.today,
        )

        # Dashboard now shows it complete.
        log = RoutineLog.objects.get(
            schedule=self.activity_schedule, scheduled_date=self.today,
        )
        self.assertEqual(log.completion_source, RoutineLog.SOURCE_MANUAL)
        self.assertIn(log.log_status, ('completed', 'completed_late'))
