"""Tests for Routine History — retroactive completion + the history screen.

Covers the trust contract for backdated routine completions:
  - A completion logged for a PAST day is flagged is_user_corrected=True and
    anchors performed_at to the target day (never "now").
  - Same-day toggles are unchanged (regression guard) — no spurious correction
    flag, real-time grace-window timing preserved.
  - The history read model (get_routine_items_for_date) reconstructs applicable
    items with the correct display_state for the visual truth badges.
  - The history view renders and the toggle/skip endpoints reject future dates.
"""

from datetime import time, timedelta

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.life.services.routine_helpers import (
    get_routine_items_for_date,
    toggle_routine_completion,
)
from apps.users.models import TermsAcceptance, User


def _onboard(user):
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()


class RetroactiveCompletionTrustTests(TestCase):
    """Backdated completions must be distinguishable from real-time ones."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="rh-trust@test.com", password="testpass123",
        )
        _onboard(self.user)
        self.routine = Routine.objects.create(
            user=self.user, name="Faith", time_of_day="morning", is_active=True,
        )
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Prayer Time",
            scheduled_time=time(7, 0), grace_period_minutes=30,
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

    def test_backdated_scheduled_is_flagged_corrected(self):
        """'On time' on a past day → completed, on-time, but is_user_corrected."""
        result = toggle_routine_completion(
            self.user, self.schedule, self.yesterday,
            completion_mode='scheduled',
        )
        self.assertTrue(result['is_completed'])
        self.assertTrue(result['is_user_corrected'])
        self.assertTrue(result['completed_as_scheduled'])

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=self.yesterday)
        self.assertEqual(log.log_status, RoutineLog.STATUS_COMPLETED)
        self.assertTrue(log.is_user_corrected)
        # performed_at anchored to the TARGET day, never "now".
        self.assertEqual(timezone.localtime(log.performed_at).date(), self.yesterday)

    def test_backdated_late_is_flagged_corrected_and_late(self):
        """'Late' on a past day → completed_late, is_user_corrected, not as-scheduled."""
        result = toggle_routine_completion(
            self.user, self.schedule, self.yesterday,
            completion_mode='late',
        )
        self.assertTrue(result['is_completed'])
        self.assertTrue(result['is_user_corrected'])
        self.assertFalse(result['completed_as_scheduled'])

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=self.yesterday)
        self.assertEqual(log.log_status, RoutineLog.STATUS_COMPLETED_LATE)
        self.assertEqual(log.timing, RoutineLog.TIMING_LATE)
        self.assertEqual(timezone.localtime(log.performed_at).date(), self.yesterday)

    def test_same_day_toggle_is_not_flagged_corrected(self):
        """Regression: a normal same-day completion is NOT a correction."""
        result = toggle_routine_completion(
            self.user, self.schedule, self.today,
            completion_mode='scheduled',
        )
        self.assertTrue(result['is_completed'])
        self.assertFalse(result['is_user_corrected'])

        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=self.today)
        self.assertFalse(log.is_user_corrected)

    def test_correcting_a_skip_on_past_day_flags_corrected(self):
        """Skipped → completed on a past day carries the correction flag."""
        RoutineLog.objects.create(
            user=self.user, schedule=self.schedule, scheduled_date=self.yesterday,
            log_status=RoutineLog.STATUS_SKIPPED, routine_at_time=self.routine,
        )
        result = toggle_routine_completion(
            self.user, self.schedule, self.yesterday, completion_mode='scheduled',
        )
        self.assertTrue(result['is_completed'])
        self.assertTrue(result['is_user_corrected'])
        log = RoutineLog.objects.get(schedule=self.schedule, scheduled_date=self.yesterday)
        self.assertTrue(log.is_user_corrected)

    def test_undo_deletes_log(self):
        """Toggling a completed past-day log with no mode deletes it (undo)."""
        toggle_routine_completion(
            self.user, self.schedule, self.yesterday, completion_mode='scheduled',
        )
        self.assertTrue(
            RoutineLog.objects.filter(schedule=self.schedule, scheduled_date=self.yesterday).exists()
        )
        result = toggle_routine_completion(self.user, self.schedule, self.yesterday)
        self.assertFalse(result['is_completed'])
        self.assertFalse(
            RoutineLog.objects.filter(schedule=self.schedule, scheduled_date=self.yesterday).exists()
        )


class RoutineHistoryReadModelTests(TestCase):
    """get_routine_items_for_date must reconstruct applicable items + state."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="rh-read@test.com", password="testpass123",
        )
        _onboard(self.user)
        self.routine = Routine.objects.create(
            user=self.user, name="Morning", time_of_day="morning", is_active=True,
        )
        self.daily = RoutineSchedule.objects.create(
            routine=self.routine, name="Prayer Time", scheduled_time=time(7, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

    def _item_for(self, history, schedule_id):
        for window in history['windows']:
            for item in window['items']:
                if item['schedule_id'] == schedule_id:
                    return item
        return None

    def test_missing_past_item_is_missed(self):
        history = get_routine_items_for_date(self.user, self.yesterday)
        item = self._item_for(history, self.daily.pk)
        self.assertIsNotNone(item)
        self.assertEqual(item['display_state'], 'missed')
        self.assertEqual(history['missed'], 1)

    def test_corrected_completion_shows_corrected_state(self):
        toggle_routine_completion(
            self.user, self.daily, self.yesterday, completion_mode='scheduled',
        )
        history = get_routine_items_for_date(self.user, self.yesterday)
        item = self._item_for(history, self.daily.pk)
        self.assertEqual(item['display_state'], 'corrected')
        self.assertTrue(item['is_completed'])
        self.assertEqual(history['completed'], 1)

    def test_real_time_completion_shows_completed_state(self):
        toggle_routine_completion(
            self.user, self.daily, self.today, completion_mode='scheduled',
        )
        history = get_routine_items_for_date(self.user, self.today)
        item = self._item_for(history, self.daily.pk)
        self.assertEqual(item['display_state'], 'completed')

    def test_skipped_shows_skipped_state(self):
        RoutineLog.objects.create(
            user=self.user, schedule=self.daily, scheduled_date=self.yesterday,
            log_status=RoutineLog.STATUS_SKIPPED, routine_at_time=self.routine,
        )
        history = get_routine_items_for_date(self.user, self.yesterday)
        item = self._item_for(history, self.daily.pk)
        self.assertEqual(item['display_state'], 'skipped')
        self.assertEqual(history['skipped'], 1)

    def test_specific_date_only_applies_to_that_date(self):
        oneoff = RoutineSchedule.objects.create(
            routine=self.routine, name="Dentist", scheduled_time=time(9, 0),
            specific_date=self.yesterday, is_active=True,
        )
        y_hist = get_routine_items_for_date(self.user, self.yesterday)
        self.assertIsNotNone(self._item_for(y_hist, oneoff.pk))
        # Not present two days ago.
        other = get_routine_items_for_date(self.user, self.yesterday - timedelta(days=1))
        self.assertIsNone(self._item_for(other, oneoff.pk))


class RoutineHistoryViewTests(TestCase):
    """The history page renders and write endpoints reject future dates."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="rh-view@test.com", password="testpass123",
        )
        _onboard(self.user)
        self.routine = Routine.objects.create(
            user=self.user, name="Morning", time_of_day="morning", is_active=True,
        )
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Prayer Time", scheduled_time=time(7, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
        )
        self.today = timezone.localdate()
        self.client.force_login(self.user)

    def test_history_page_renders(self):
        resp = self.client.get(reverse('life:routine_history'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Routine History")

    def test_history_page_accepts_date_param(self):
        d = (self.today - timedelta(days=3)).isoformat()
        resp = self.client.get(reverse('life:routine_history'), {'date': d})
        self.assertEqual(resp.status_code, 200)

    def test_toggle_rejects_future_date(self):
        future = (self.today + timedelta(days=2)).isoformat()
        resp = self.client.post(reverse('life:routine_toggle'), {
            'schedule_id': self.schedule.pk, 'date': future,
            'completion_mode': 'scheduled',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertFalse(RoutineLog.objects.filter(schedule=self.schedule).exists())

    def test_skip_rejects_future_date(self):
        future = (self.today + timedelta(days=2)).isoformat()
        resp = self.client.post(reverse('life:routine_skip'), {
            'schedule_id': self.schedule.pk, 'date': future,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    def test_toggle_past_date_via_endpoint_sets_correction(self):
        yesterday = (self.today - timedelta(days=1)).isoformat()
        resp = self.client.post(reverse('life:routine_toggle'), {
            'schedule_id': self.schedule.pk, 'date': yesterday,
            'completion_mode': 'late',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_user_corrected'])
        log = RoutineLog.objects.get(schedule=self.schedule)
        self.assertTrue(log.is_user_corrected)
        self.assertEqual(log.log_status, RoutineLog.STATUS_COMPLETED_LATE)
