"""
Recurring Event Duplicate Detection Tests.

Validates that CalendarMutationService.create() detects duplicates against
recurring event occurrences — not just the base row's exact start_dt.

Covers:
1. Adding event that matches a recurring occurrence → reused=True
2. Adding event with same title but different time → allowed (new event)
3. Adding event with different title at same time → allowed (new event)
4. Non-recurring event with same title, different date → allowed
5. Canceled recurring event does NOT block new creation
6. Case-insensitive title matching against recurrence
7. Occurrence match inside transaction (race-safe path)
"""

import datetime as dt
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from freezegun import freeze_time

from apps.calendar_engine.models import CalendarEvent, RecurrenceRule
from apps.calendar_engine.services.calendar_mutation_service import (
    CalendarMutationService,
)
from apps.calendar_engine.utils.idempotency import compute_idempotency_key

User = get_user_model()

EST = ZoneInfo('America/New_York')


def _make_event(user, title, start_dt, end_dt=None, is_protected=False):
    """Helper: create a CalendarEvent with proper idempotency key."""
    if end_dt is None:
        end_dt = start_dt + dt.timedelta(hours=1)
    idem_key = compute_idempotency_key(user.id, title, start_dt, end_dt=end_dt)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start_dt,
        end_dt=end_dt,
        idempotency_key=idem_key,
        status=CalendarEvent.STATUS_SCHEDULED,
        is_protected=is_protected,
    )


def _make_recurring(event, frequency='weekly', byweekday=None, interval=1):
    """Attach a RecurrenceRule to an existing CalendarEvent."""
    return RecurrenceRule.objects.create(
        event=event,
        frequency=frequency,
        byweekday=byweekday or [],
        interval=interval,
    )


class _RecurrenceUserMixin:
    def _create_user(self, email='recurtest@example.com'):
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(
            email=email, password='testpass123', first_name='Recur',
        )
        prefs = user.preferences
        prefs.timezone = 'America/New_York'
        prefs.has_completed_onboarding = True
        prefs.save()

        terms_version = django_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=terms_version)
        return user


@freeze_time("2026-02-24 12:00:00")
class TestRecurrenceDuplicateDetection(_RecurrenceUserMixin, TestCase):
    """Recurring-event duplicate detection in CalendarMutationService."""

    def setUp(self):
        self.user = self._create_user()
        # Base event: Workout on Thursday Feb 26 at 6:15am EST (11:15 UTC)
        self.base_start = dt.datetime(2026, 2, 26, 11, 15, tzinfo=dt.timezone.utc)
        self.base_end = self.base_start + dt.timedelta(hours=1)
        self.base_event = _make_event(
            self.user, 'Workout', self.base_start, self.base_end,
            is_protected=True,
        )
        # Weekly recurrence — every Thursday
        _make_recurring(self.base_event, frequency='weekly')
        self.svc = CalendarMutationService(self.user)

    def test_duplicate_occurrence_detected(self):
        """Creating an event that matches a future occurrence → reused."""
        # Next Thursday = March 5, same time
        next_thursday = dt.datetime(2026, 3, 5, 11, 15, tzinfo=dt.timezone.utc)
        end = next_thursday + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(
            self.user.id, 'Workout', next_thursday, end_dt=end,
        )
        result = self.svc.create(
            title='Workout',
            start_dt=next_thursday,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.reused)
        self.assertEqual(result.event.pk, self.base_event.pk)

    def test_same_title_different_time_allowed(self):
        """Same title on occurrence day but different time → new event."""
        # March 5 at 7:00am EST (12:00 UTC) — different from 6:15am
        diff_time = dt.datetime(2026, 3, 5, 12, 0, tzinfo=dt.timezone.utc)
        end = diff_time + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(
            self.user.id, 'Workout', diff_time, end_dt=end,
        )
        result = self.svc.create(
            title='Workout',
            start_dt=diff_time,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)
        self.assertNotEqual(result.event.pk, self.base_event.pk)

    def test_different_title_same_time_allowed(self):
        """Different title at an occurrence time → new event."""
        next_thursday = dt.datetime(2026, 3, 5, 11, 15, tzinfo=dt.timezone.utc)
        end = next_thursday + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(
            self.user.id, 'Yoga', next_thursday, end_dt=end,
        )
        result = self.svc.create(
            title='Yoga',
            start_dt=next_thursday,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)

    def test_case_insensitive_title_match(self):
        """Title matching is case-insensitive against recurring events."""
        next_thursday = dt.datetime(2026, 3, 5, 11, 15, tzinfo=dt.timezone.utc)
        end = next_thursday + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(
            self.user.id, 'WORKOUT', next_thursday, end_dt=end,
        )
        result = self.svc.create(
            title='WORKOUT',
            start_dt=next_thursday,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.reused)
        self.assertEqual(result.event.pk, self.base_event.pk)

    def test_canceled_recurring_does_not_block(self):
        """Canceled recurring event doesn't prevent new creation."""
        self.base_event.status = CalendarEvent.STATUS_CANCELED
        self.base_event.save()

        next_thursday = dt.datetime(2026, 3, 5, 11, 15, tzinfo=dt.timezone.utc)
        end = next_thursday + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(
            self.user.id, 'Workout', next_thursday, end_dt=end,
        )
        result = self.svc.create(
            title='Workout',
            start_dt=next_thursday,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)

    def test_non_recurring_same_title_different_date_allowed(self):
        """Non-recurring event with same title but different date → new event."""
        # Create a non-recurring Workout (no RecurrenceRule)
        standalone = _make_event(
            self.user, 'Cardio', self.base_start, self.base_end,
        )
        # Try to add Cardio on a different day
        diff_day = dt.datetime(2026, 3, 3, 11, 15, tzinfo=dt.timezone.utc)
        end = diff_day + dt.timedelta(hours=1)
        idem_key = compute_idempotency_key(
            self.user.id, 'Cardio', diff_day, end_dt=end,
        )
        result = self.svc.create(
            title='Cardio',
            start_dt=diff_day,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertFalse(result.reused)

    def test_base_event_date_still_caught_by_semantic_dedup(self):
        """The original base event date is caught by regular semantic dedup."""
        end = self.base_end
        idem_key = compute_idempotency_key(
            self.user.id, 'Workout', self.base_start, end_dt=end,
        )
        result = self.svc.create(
            title='Workout',
            start_dt=self.base_start,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.reused)
        self.assertEqual(result.event.pk, self.base_event.pk)


class ReAddAfterSoftDeleteTests(TestCase):
    """
    Regression tests: soft-deleted events must not block re-creation.

    Covers the bug where idempotency_key check returned a canceled event
    with reused=True, causing "no duplicate created" instead of creating
    a new event.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='readd@test.com', password='test1234',
        )
        self.svc = CalendarMutationService(self.user)
        self.start_dt = dt.datetime(2026, 2, 26, 10, 0, tzinfo=EST)
        self.end_dt = self.start_dt + dt.timedelta(hours=1)
        self.title = 'WFM Interface Discussion'

    @freeze_time('2026-02-24 18:00:00')
    def test_readd_after_soft_delete_creates_new_event(self):
        """Delete then re-add the same event → new event, not reused."""
        idem_key = compute_idempotency_key(
            self.user.id, self.title, self.start_dt, end_dt=self.end_dt,
        )

        # Create
        r1 = self.svc.create(
            title=self.title, start_dt=self.start_dt, end_dt=self.end_dt,
            idempotency_key=idem_key,
        )
        self.assertTrue(r1.success)
        self.assertFalse(r1.reused)
        original_pk = r1.event.pk

        # Delete (soft)
        r_del = self.svc.delete(original_pk)
        self.assertTrue(r_del.success)

        # Re-add with same parameters
        r2 = self.svc.create(
            title=self.title, start_dt=self.start_dt, end_dt=self.end_dt,
            idempotency_key=idem_key,
        )
        self.assertTrue(r2.success)
        self.assertFalse(r2.reused, "Should create a NEW event, not return the deleted one")
        self.assertNotEqual(r2.event.pk, original_pk)
        self.assertEqual(r2.event.status, CalendarEvent.STATUS_SCHEDULED)
        self.assertIsNone(r2.event.deleted_at)

    @freeze_time('2026-02-24 18:00:00')
    def test_semantic_dup_excludes_soft_deleted(self):
        """Semantic duplicate check must not match soft-deleted events."""
        idem_key = compute_idempotency_key(
            self.user.id, self.title, self.start_dt, end_dt=self.end_dt,
        )

        # Create and delete
        r1 = self.svc.create(
            title=self.title, start_dt=self.start_dt, end_dt=self.end_dt,
            idempotency_key=idem_key,
        )
        self.svc.delete(r1.event.pk)

        # Re-add with a DIFFERENT idempotency key (same title + time)
        idem_key2 = compute_idempotency_key(
            self.user.id, self.title, self.start_dt, end_dt=self.end_dt,
            source_type='manual', source_id='retry-1',
        )
        r2 = self.svc.create(
            title=self.title, start_dt=self.start_dt, end_dt=self.end_dt,
            idempotency_key=idem_key2,
        )
        self.assertTrue(r2.success)
        self.assertFalse(r2.reused)

    @freeze_time('2026-02-24 18:00:00')
    def test_active_event_still_detected_as_duplicate(self):
        """Active (non-deleted) event still returns reused=True."""
        idem_key = compute_idempotency_key(
            self.user.id, self.title, self.start_dt, end_dt=self.end_dt,
        )

        r1 = self.svc.create(
            title=self.title, start_dt=self.start_dt, end_dt=self.end_dt,
            idempotency_key=idem_key,
        )
        # Re-add without deleting first
        r2 = self.svc.create(
            title=self.title, start_dt=self.start_dt, end_dt=self.end_dt,
            idempotency_key=idem_key,
        )
        self.assertTrue(r2.success)
        self.assertTrue(r2.reused, "Active event should still be detected as duplicate")
        self.assertEqual(r2.event.pk, r1.event.pk)
