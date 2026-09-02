"""
Regression tests for the recurring-occurrence edit integrity bug.

Incident (2026-07-07, "Check on Von's House"): a recurring task whose series
began on 7/5. The user edited today's occurrence and assigned a time (5:00 PM).
Immediately after saving the task became OVERDUE, and after completing it the
whole series disappeared.

Proven root cause:
  1. FORM: the recurring-task edit form disabled the due_date input in recurring
     mode. A disabled <input> is not submitted, so the ModelForm blanked
     Task.due_date on every recurring-task save.
  2. MODEL: Task.save() then backfilled the blank due_date from start_date (the
     series start, 7/5 — a PAST date), so the task was born overdue. Completion
     anchored next-occurrence generation on that stale past due_date, so no valid
     future occurrence surfaced ("series disappeared").

These tests lock in the fix at both layers.
"""
import datetime as dt
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.life.models import Task
from apps.users.models import User, TermsAcceptance


def _today():
    return timezone.now().date()


class RecurringDueDateBackfillTests(TestCase):
    """Model layer: a blank due_date on a recurring task must never resolve to a
    date in the past."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="recur-model@test.com", password="testpass123"
        )

    def test_past_start_no_due_date_resolves_to_today_not_past(self):
        """Daily series that started 2 days ago, blank due_date → due today,
        NOT the past start_date. (This is the exact born-overdue mechanism.)"""
        start = _today() - dt.timedelta(days=2)
        task = Task(
            user=self.user,
            title="Check on Von's House",
            is_recurring=True,
            recurrence_pattern="daily",
            start_date=start,
            due_date=None,
        )
        task.save()
        task.refresh_from_db()

        self.assertEqual(task.due_date, _today(),
                         "Blank due_date must resolve to today, not the past start.")
        self.assertGreaterEqual(task.due_date, _today())
        self.assertFalse(task.is_overdue,
                         "A freshly-scheduled recurring occurrence must not be overdue.")

    def test_weekly_past_start_stays_pattern_aligned_and_future(self):
        """Weekly series started 10 days ago, blank due_date → first weekly
        occurrence on/after today (pattern-aligned, never past)."""
        start = _today() - dt.timedelta(days=10)
        task = Task(
            user=self.user,
            title="Weekly check",
            is_recurring=True,
            recurrence_pattern="weekly",
            start_date=start,
            due_date=None,
        )
        task.save()
        task.refresh_from_db()

        self.assertGreaterEqual(task.due_date, _today())
        self.assertEqual((task.due_date - start).days % 7, 0,
                         "Resolved due_date must stay aligned to the weekly cadence.")

    def test_future_start_is_preserved(self):
        """A future start_date is still honored (not clamped to today)."""
        start = _today() + dt.timedelta(days=3)
        task = Task(
            user=self.user,
            title="Future series",
            is_recurring=True,
            recurrence_pattern="daily",
            start_date=start,
            due_date=None,
        )
        task.save()
        task.refresh_from_db()
        self.assertEqual(task.due_date, start)


class RecurringOccurrenceEditViewTests(TestCase):
    """The clock is pinned to 08:00 today (see `setUp`).

    These tests assign a scheduled_time of 17:00 to an occurrence due TODAY and assert
    it is not overdue. With a real clock that is only true before 5pm — the suite passed
    in the morning and failed in the evening. Pinning it makes the assertion about the
    FORM behaviour it is named for (omitting due_date must not clear it) rather than
    about what time the suite happens to run.
    """

    """End-to-end: edit today's occurrence through TaskUpdateView the way the
    production UI does, and prove it is not born overdue and the series survives
    completion."""

    def setUp(self):
        patcher = mock.patch(
            "apps.core.utils.get_user_now",
            return_value=timezone.now().replace(hour=8, minute=0, second=0,
                                                microsecond=0))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_user(
            email="recur-view@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.life_enabled = True
        self.user.preferences.save()
        self.client.login(email="recur-view@test.com", password="testpass123")

    def _make_recurring_occurrence(self):
        # Mirrors production: series began a couple of days ago; today's
        # occurrence exists with NO execution time (scheduled_time is NULL).
        return Task.objects.create(
            user=self.user,
            title="Check on Von's House",
            is_recurring=True,
            recurrence_pattern="daily",
            start_date=_today() - dt.timedelta(days=2),
            due_date=_today(),
            scheduled_time=None,
        )

    def test_edit_without_due_date_field_does_not_go_overdue(self):
        """Reproduces the incident: POST omits due_date (old form disabled the
        input) but assigns scheduled_time. Task must NOT become overdue."""
        task = self._make_recurring_occurrence()
        url = reverse("life:task_update", kwargs={"pk": task.pk})

        # Note: NO 'due_date' key — exactly what the browser sent when the input
        # was disabled in recurring mode.
        resp = self.client.post(url, {
            "title": "Check on Von's House",
            "is_recurring": "on",
            "recurrence_pattern": "daily",
            "start_date": (_today() - dt.timedelta(days=2)).isoformat(),
            "scheduled_time": "17:00",
            "completion_status": "pending",
            "progress_percentage": "0",
            "effort": "medium",
            "commitment_level": "flexible",
        })
        self.assertEqual(resp.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.scheduled_time, dt.time(17, 0))
        self.assertGreaterEqual(task.due_date, _today(),
                                "due_date must not be reset to the past series start.")
        self.assertFalse(task.is_overdue,
                         "Assigning a time to today's occurrence must not make it overdue.")

    def test_edit_with_due_date_field_round_trips(self):
        """With the form fix the browser submits due_date (visible + enabled).
        Setting it to today keeps the occurrence scheduled for today."""
        task = self._make_recurring_occurrence()
        url = reverse("life:task_update", kwargs={"pk": task.pk})

        resp = self.client.post(url, {
            "title": "Check on Von's House",
            "is_recurring": "on",
            "recurrence_pattern": "daily",
            "due_date": _today().isoformat(),
            "start_date": (_today() - dt.timedelta(days=2)).isoformat(),
            "scheduled_time": "17:00",
            "completion_status": "pending",
            "progress_percentage": "0",
            "effort": "medium",
            "commitment_level": "flexible",
        })
        self.assertEqual(resp.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.due_date, _today())
        self.assertEqual(task.scheduled_time, dt.time(17, 0))
        self.assertFalse(task.is_overdue)

    def test_completing_edited_occurrence_generates_future_and_keeps_series(self):
        """Completing today's (correctly-dated) occurrence generates the NEXT
        FUTURE occurrence — the series does not disappear."""
        task = self._make_recurring_occurrence()
        url = reverse("life:task_update", kwargs={"pk": task.pk})
        self.client.post(url, {
            "title": "Check on Von's House",
            "is_recurring": "on",
            "recurrence_pattern": "daily",
            "start_date": (_today() - dt.timedelta(days=2)).isoformat(),
            "scheduled_time": "17:00",
            "completion_status": "pending",
            "progress_percentage": "0",
            "effort": "medium",
            "commitment_level": "flexible",
        })
        task.refresh_from_db()

        task.mark_complete()

        # A pending FUTURE occurrence must now exist.
        future = Task.objects.filter(
            user=self.user,
            title="Check on Von's House",
            is_recurring=True,
            completion_status="pending",
            due_date__gte=_today(),
        ).order_by("due_date").first()
        self.assertIsNotNone(future, "Completing the occurrence must generate the next one.")
        self.assertGreater(future.due_date, _today() - dt.timedelta(days=1))
        self.assertFalse(future.is_overdue, "The generated next occurrence must not be overdue.")
        # Series anchor intact.
        self.assertTrue(future.is_recurring)
        self.assertEqual(future.recurrence_pattern, "daily")
