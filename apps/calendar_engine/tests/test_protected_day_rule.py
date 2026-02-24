"""
Protected Event Day-Change Rule Tests.

Validates:
1. Protected events CAN be moved within the same day (time-only change).
2. Protected events CANNOT be moved to a different day.
3. Unprotected events CAN be moved cross-day normally.
4. force=True does NOT bypass the protected day-change rule.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from freezegun import freeze_time

from apps.calendar_engine.models import CalendarEvent
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


class _ProtectedUserMixin:
    def _create_user(self, email='prottest@example.com'):
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(
            email=email, password='testpass123', first_name='Prot',
        )
        prefs = user.preferences
        prefs.timezone = 'America/New_York'
        prefs.has_completed_onboarding = True
        prefs.save()

        terms_version = django_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=terms_version)
        return user


# ──────────────────────────────────────────────────────────
# 1) Protected same-day update is ALLOWED
# ──────────────────────────────────────────────────────────

class TestProtectedSameDayUpdateAllowed(_ProtectedUserMixin, TestCase):

    def setUp(self):
        self.user = self._create_user()

    @freeze_time("2026-02-25 10:00:00")
    def test_protected_same_day_time_change(self):
        """Moving a protected event to a different time on the same day succeeds."""
        wed = dt.datetime(2026, 2, 25, 6, 15, tzinfo=EST)
        ev = _make_event(self.user, 'Workout', wed, is_protected=True)

        service = CalendarMutationService(self.user)
        new_start = dt.datetime(2026, 2, 25, 7, 0, tzinfo=EST)
        new_end = dt.datetime(2026, 2, 25, 8, 0, tzinfo=EST)

        result = service.update(ev.pk, start_dt=new_start, end_dt=new_end)

        self.assertTrue(result.success,
                         f"Same-day move should succeed but got: {result.error}")
        ev.refresh_from_db()
        local = ev.start_dt.astimezone(EST)
        self.assertEqual(local.hour, 7)

    @freeze_time("2026-02-25 10:00:00")
    def test_protected_same_day_with_force(self):
        """force=True on a same-day move also succeeds (no conflict to override)."""
        wed = dt.datetime(2026, 2, 25, 6, 15, tzinfo=EST)
        ev = _make_event(self.user, 'Workout', wed, is_protected=True)

        service = CalendarMutationService(self.user)
        new_start = dt.datetime(2026, 2, 25, 8, 0, tzinfo=EST)
        new_end = dt.datetime(2026, 2, 25, 9, 0, tzinfo=EST)

        result = service.update(ev.pk, force=True, start_dt=new_start, end_dt=new_end)

        self.assertTrue(result.success)
        ev.refresh_from_db()
        self.assertEqual(ev.start_dt.astimezone(EST).hour, 8)


# ──────────────────────────────────────────────────────────
# 2) Protected cross-day update is BLOCKED
# ──────────────────────────────────────────────────────────

class TestProtectedCrossDayUpdateBlocked(_ProtectedUserMixin, TestCase):

    def setUp(self):
        self.user = self._create_user('crossday@example.com')

    @freeze_time("2026-02-25 10:00:00")
    def test_protected_cross_day_blocked(self):
        """Moving a protected event to a different day is blocked."""
        wed = dt.datetime(2026, 2, 25, 6, 15, tzinfo=EST)
        ev = _make_event(self.user, 'Workout', wed, is_protected=True)

        service = CalendarMutationService(self.user)
        # Move to Thursday
        thu = dt.datetime(2026, 2, 26, 6, 15, tzinfo=EST)
        thu_end = dt.datetime(2026, 2, 26, 7, 15, tzinfo=EST)

        result = service.update(ev.pk, start_dt=thu, end_dt=thu_end)

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
        self.assertIn('protected', result.error.lower())
        self.assertIn('cannot be moved', result.error.lower())

        # Event must NOT have changed
        ev.refresh_from_db()
        self.assertEqual(ev.start_dt.astimezone(EST).date(), dt.date(2026, 2, 25))

    @freeze_time("2026-02-25 10:00:00")
    def test_protected_cross_day_message_includes_title(self):
        """Blocked message includes the event title."""
        wed = dt.datetime(2026, 2, 25, 6, 15, tzinfo=EST)
        ev = _make_event(self.user, 'Bible Study', wed, is_protected=True)

        service = CalendarMutationService(self.user)
        fri = dt.datetime(2026, 2, 27, 6, 15, tzinfo=EST)

        result = service.update(ev.pk, start_dt=fri, end_dt=fri + dt.timedelta(hours=1))

        self.assertFalse(result.success)
        self.assertIn('Bible Study', result.error)


# ──────────────────────────────────────────────────────────
# 3) Unprotected cross-day update is ALLOWED
# ──────────────────────────────────────────────────────────

class TestUnprotectedCrossDayAllowed(_ProtectedUserMixin, TestCase):

    def setUp(self):
        self.user = self._create_user('unprotected@example.com')

    @freeze_time("2026-02-25 10:00:00")
    def test_unprotected_cross_day_allowed(self):
        """Moving an unprotected event to a different day succeeds."""
        wed = dt.datetime(2026, 2, 25, 14, 0, tzinfo=EST)
        ev = _make_event(self.user, 'Casual Meeting', wed, is_protected=False)

        service = CalendarMutationService(self.user)
        thu = dt.datetime(2026, 2, 26, 14, 0, tzinfo=EST)
        thu_end = dt.datetime(2026, 2, 26, 15, 0, tzinfo=EST)

        result = service.update(ev.pk, force=True, start_dt=thu, end_dt=thu_end)

        self.assertTrue(result.success,
                         f"Unprotected cross-day move should succeed: {result.error}")
        ev.refresh_from_db()
        self.assertEqual(ev.start_dt.astimezone(EST).date(), dt.date(2026, 2, 26))


# ──────────────────────────────────────────────────────────
# 4) force_override does NOT bypass protected day rule
# ──────────────────────────────────────────────────────────

class TestForceDoesNotBypassProtected(_ProtectedUserMixin, TestCase):

    def setUp(self):
        self.user = self._create_user('forcetest@example.com')

    @freeze_time("2026-02-25 10:00:00")
    def test_force_override_does_not_bypass_protected_day_rule(self):
        """force=True must NOT allow a protected event to move cross-day."""
        wed = dt.datetime(2026, 2, 25, 6, 15, tzinfo=EST)
        ev = _make_event(self.user, 'Workout', wed, is_protected=True)

        service = CalendarMutationService(self.user)
        thu = dt.datetime(2026, 2, 26, 6, 15, tzinfo=EST)
        thu_end = dt.datetime(2026, 2, 26, 7, 15, tzinfo=EST)

        # Even with force=True, cross-day move is blocked for protected events
        result = service.update(ev.pk, force=True, start_dt=thu, end_dt=thu_end)

        self.assertFalse(result.success,
                          "force=True should NOT bypass protected day-change rule")
        self.assertTrue(result.requires_decision)
        self.assertIn('protected', result.error.lower())

        # Event must remain on original day
        ev.refresh_from_db()
        self.assertEqual(ev.start_dt.astimezone(EST).date(), dt.date(2026, 2, 25))

    @freeze_time("2026-02-25 10:00:00")
    def test_auto_protected_workout_blocked_cross_day(self):
        """
        Events auto-protected by title pattern (e.g. 'Workout')
        are also blocked from cross-day moves.
        """
        wed = dt.datetime(2026, 2, 25, 6, 15, tzinfo=EST)
        # Auto-protect fires on create via CMS
        service = CalendarMutationService(self.user)
        create_result = service.create(
            title='Workout',
            start_dt=wed,
            end_dt=wed + dt.timedelta(hours=1),
        )
        self.assertTrue(create_result.success)
        ev = create_result.event
        self.assertTrue(ev.is_protected, "Workout should be auto-protected")

        # Try to move cross-day with force
        thu = dt.datetime(2026, 2, 26, 6, 15, tzinfo=EST)
        result = service.update(
            ev.pk, force=True,
            start_dt=thu, end_dt=thu + dt.timedelta(hours=1),
        )

        self.assertFalse(result.success)
        self.assertTrue(result.requires_decision)
