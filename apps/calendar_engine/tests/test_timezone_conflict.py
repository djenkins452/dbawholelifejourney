"""
Timezone-aware conflict detection and gap calculation tests.

Validates that:
1. Events scheduled in user's local time display correctly in conflict messages
   (no UTC shift — 6:15 AM local must report as 6:15 AM, not 11:15 AM).
2. Gap calculation returns durations and boundaries in user's local timezone.
3. No double timezone conversion occurs.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.services.calendar_mutation_service import (
    CalendarMutationService,
)
from apps.calendar_engine.services.conflicts import (
    detect_all_conflicts,
    build_conflict_message,
    classify_conflict_case,
)
from apps.calendar_engine.services.suggestions import find_gaps_for_day
from apps.calendar_engine.utils.idempotency import compute_idempotency_key

User = get_user_model()

EST = ZoneInfo('America/New_York')      # UTC-5
CST = ZoneInfo('America/Chicago')       # UTC-6


def _make_event(user, title, start_dt, end_dt, **kwargs):
    """Helper: create a CalendarEvent with proper idempotency key."""
    idem_key = compute_idempotency_key(user.id, title, start_dt, end_dt=end_dt)
    return CalendarEvent.objects.create(
        user=user,
        title=title,
        start_dt=start_dt,
        end_dt=end_dt,
        idempotency_key=idem_key,
        status=kwargs.pop('status', CalendarEvent.STATUS_SCHEDULED),
        **kwargs,
    )


class _TZUserMixin:
    """Setup helper: creates a user with a specific timezone."""

    def _create_user(self, email='tztest@example.com', tz_name='America/New_York'):
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance

        user = User.objects.create_user(
            email=email,
            password='testpass123',
            first_name='TZ',
        )
        prefs = user.preferences
        prefs.timezone = tz_name
        prefs.has_completed_onboarding = True
        prefs.save()

        terms_version = django_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(
            user=user,
            terms_version=terms_version,
        )
        return user


# ──────────────────────────────────────────────────────────
# 1) Conflict detection reports local time, not UTC
# ──────────────────────────────────────────────────────────

class TestConflictDetectionTimezone(_TZUserMixin, TestCase):
    """
    Schedule 6:15 AM in user timezone (EST = UTC-5).
    Stored in UTC as 11:15 AM.
    Conflict detection must compare in local time and report 6:15 AM.
    """

    def setUp(self):
        self.user = self._create_user(tz_name='America/New_York')

    @freeze_time("2026-02-24 10:00:00")  # 5:00 AM EST
    def test_conflict_reports_local_time_not_utc(self):
        """Conflicting event time should be in user's local timezone."""
        existing_start = dt.datetime(2026, 2, 24, 6, 15, tzinfo=EST)
        existing_end = dt.datetime(2026, 2, 24, 7, 15, tzinfo=EST)

        _make_event(self.user, "Morning Routine", existing_start, existing_end)

        # Propose a new event overlapping at 6:30 AM EST
        new_start = dt.datetime(2026, 2, 24, 6, 30, tzinfo=EST)
        new_end = dt.datetime(2026, 2, 24, 7, 30, tzinfo=EST)

        result = detect_all_conflicts(self.user, new_start, new_end)

        self.assertTrue(result['has_conflict'])
        self.assertEqual(len(result['conflicts']), 1)

        conflict = result['conflicts'][0]
        # The ISO string must reflect EST (UTC-5), not UTC
        self.assertIn('06:15', conflict['start_dt'],
                       f"Expected 06:15 (local) but got {conflict['start_dt']}")
        self.assertIn('07:15', conflict['end_dt'],
                       f"Expected 07:15 (local) but got {conflict['end_dt']}")
        # Must NOT contain 11:15 (UTC)
        self.assertNotIn('11:15', conflict['start_dt'],
                          "Conflict time is in UTC — should be local")

    @freeze_time("2026-02-24 10:00:00")
    def test_conflict_message_shows_local_time(self):
        """The user-facing conflict message must show local time."""
        existing_start = dt.datetime(2026, 2, 24, 6, 15, tzinfo=EST)
        existing_end = dt.datetime(2026, 2, 24, 7, 15, tzinfo=EST)

        _make_event(self.user, "Morning Routine", existing_start, existing_end)

        new_start = dt.datetime(2026, 2, 24, 6, 30, tzinfo=EST)
        new_end = dt.datetime(2026, 2, 24, 7, 30, tzinfo=EST)

        # Activate user's timezone (simulating middleware)
        timezone.activate(EST)
        try:
            result = detect_all_conflicts(self.user, new_start, new_end)
            case = classify_conflict_case(result['conflicts'], False)
            message = build_conflict_message(case, result['conflicts'])
        finally:
            timezone.deactivate()

        # Message must show "6:15am", not "11:15am"
        self.assertIn('6:15am', message,
                       f"Expected '6:15am' in message but got: {message}")
        self.assertNotIn('11:15', message,
                          f"UTC time leaked into message: {message}")


# ──────────────────────────────────────────────────────────
# 2) Gap calculation: correct duration and local boundaries
# ──────────────────────────────────────────────────────────

class TestGapCalculationTimezone(_TZUserMixin, TestCase):
    """
    Given two events: 6:15–7:15 and 8:00–9:00 (user local time),
    the suggested gap must be 7:15–8:00 = 45 min, in local time.
    """

    def setUp(self):
        self.user = self._create_user(tz_name='America/New_York')

    @freeze_time("2026-02-24 10:00:00")
    def test_gap_between_events_correct_duration(self):
        """Gap between 7:15 and 8:00 = 45 minutes (below MIN_GAP)."""
        # Event 1: 6:15 AM – 7:15 AM EST
        _make_event(
            self.user, "Morning Routine",
            dt.datetime(2026, 2, 24, 6, 15, tzinfo=EST),
            dt.datetime(2026, 2, 24, 7, 15, tzinfo=EST),
        )
        # Event 2: 8:00 AM – 9:00 AM EST
        _make_event(
            self.user, "Team Standup",
            dt.datetime(2026, 2, 24, 8, 0, tzinfo=EST),
            dt.datetime(2026, 2, 24, 9, 0, tzinfo=EST),
        )

        timezone.activate(EST)
        try:
            gaps = find_gaps_for_day(self.user, date=dt.date(2026, 2, 24))
        finally:
            timezone.deactivate()

        # The 45-min gap (7:15–8:00) is below MIN_GAP_MINUTES (90), filtered out.
        # Verify the large gap after the second event exists and is correct.
        post_gap = None
        for g in gaps:
            local_start = g['start_dt'].astimezone(EST)
            if local_start.hour == 9 and local_start.minute == 0:
                post_gap = g
                break

        self.assertIsNotNone(post_gap,
                              f"Expected gap starting at 9:00am. Gaps: {gaps}")
        # 9:00 AM to 10:00 PM = 13 hours = 780 minutes
        self.assertEqual(post_gap['duration_minutes'], 780)

    @freeze_time("2026-02-24 10:00:00")
    def test_gap_times_in_local_timezone(self):
        """Gap start/end datetimes must be in user's local timezone."""
        _make_event(
            self.user, "Lunch",
            dt.datetime(2026, 2, 24, 12, 0, tzinfo=EST),
            dt.datetime(2026, 2, 24, 13, 0, tzinfo=EST),
        )

        timezone.activate(EST)
        try:
            gaps = find_gaps_for_day(self.user, date=dt.date(2026, 2, 24))
        finally:
            timezone.deactivate()

        self.assertTrue(len(gaps) >= 1, "Expected at least one gap")

        # First gap should be 6:00 AM – 12:00 PM local
        first_gap = gaps[0]
        local_start = first_gap['start_dt'].astimezone(EST)
        local_end = first_gap['end_dt'].astimezone(EST)

        self.assertEqual(local_start.hour, 6)
        self.assertEqual(local_start.minute, 0)
        self.assertEqual(local_end.hour, 12)
        self.assertEqual(local_end.minute, 0)
        self.assertEqual(first_gap['duration_minutes'], 360)  # 6 hours

        # Verify the gap datetimes are in EST, not UTC
        # The offset for EST in February is -05:00
        gap_start_offset = first_gap['start_dt'].utcoffset()
        expected_offset = dt.timedelta(hours=-5)
        self.assertEqual(gap_start_offset, expected_offset,
                          f"Gap start timezone offset is {gap_start_offset}, "
                          f"expected {expected_offset} (EST)")


# ──────────────────────────────────────────────────────────
# 3) No double timezone conversion
# ──────────────────────────────────────────────────────────

class TestNoDoubleConversion(_TZUserMixin, TestCase):
    """
    If start_dt is already in user timezone, ensure no double conversion
    shifts it by an additional offset.
    """

    def setUp(self):
        self.user = self._create_user(tz_name='America/New_York')

    @freeze_time("2026-02-24 10:00:00")
    def test_already_local_time_not_shifted(self):
        """
        An event created with user-tz-aware datetime should NOT get shifted
        again when returned by conflict detection.
        """
        start = dt.datetime(2026, 2, 24, 6, 15, tzinfo=EST)
        end = dt.datetime(2026, 2, 24, 7, 15, tzinfo=EST)

        _make_event(self.user, "Test Event", start, end)

        # Query with an overlapping time — also in EST
        q_start = dt.datetime(2026, 2, 24, 6, 0, tzinfo=EST)
        q_end = dt.datetime(2026, 2, 24, 8, 0, tzinfo=EST)

        result = detect_all_conflicts(self.user, q_start, q_end)
        conflict = result['conflicts'][0]

        # Parse the returned ISO string
        from datetime import datetime as _dt
        returned_start = _dt.fromisoformat(conflict['start_dt'])

        # Must be 6:15 AM in EST (or equivalent)
        self.assertEqual(returned_start.astimezone(EST).hour, 6)
        self.assertEqual(returned_start.astimezone(EST).minute, 15)

        # Check it's NOT 1:15 AM (double-subtracted 5 hours)
        self.assertNotEqual(returned_start.astimezone(EST).hour, 1,
                             "Double timezone conversion detected!")

    @freeze_time("2026-02-24 10:00:00")
    def test_cms_conflict_times_match_input(self):
        """
        CalendarMutationService conflict detection must return times
        that match the original event's local time.
        """
        _make_event(
            self.user, "Existing Event",
            dt.datetime(2026, 2, 24, 6, 15, tzinfo=EST),
            dt.datetime(2026, 2, 24, 7, 15, tzinfo=EST),
        )

        cms = CalendarMutationService(self.user)
        result = cms.create(
            title="New Event",
            start_dt=dt.datetime(2026, 2, 24, 6, 30, tzinfo=EST),
            end_dt=dt.datetime(2026, 2, 24, 7, 30, tzinfo=EST),
        )

        self.assertTrue(result.requires_decision)
        self.assertIsNotNone(result.conflict_details)

        conflict = result.conflict_details['conflicts'][0]
        # Must show 6:15 AM (local), not 11:15 AM (UTC)
        self.assertIn('06:15', conflict['start_dt'],
                       f"Expected 06:15 but got {conflict['start_dt']}")


# ──────────────────────────────────────────────────────────
# 4) CST timezone (UTC-6) — different offset
# ──────────────────────────────────────────────────────────

class TestCSTTimezone(_TZUserMixin, TestCase):
    """Verify with America/Chicago (UTC-6) to confirm no offset hardcoding."""

    def setUp(self):
        self.user = self._create_user(
            email='cstuser@example.com', tz_name='America/Chicago',
        )

    @freeze_time("2026-02-24 10:00:00")
    def test_cst_conflict_shows_local_time(self):
        """CST user: 6:15 AM CST = 12:15 PM UTC — must report 6:15 AM."""
        _make_event(
            self.user, "Morning Prayer",
            dt.datetime(2026, 2, 24, 6, 15, tzinfo=CST),
            dt.datetime(2026, 2, 24, 7, 15, tzinfo=CST),
        )

        new_start = dt.datetime(2026, 2, 24, 6, 30, tzinfo=CST)
        new_end = dt.datetime(2026, 2, 24, 7, 30, tzinfo=CST)

        result = detect_all_conflicts(self.user, new_start, new_end)
        conflict = result['conflicts'][0]

        self.assertIn('06:15', conflict['start_dt'],
                       f"Expected 06:15 (CST local) but got {conflict['start_dt']}")
        # Must NOT be 12:15 (UTC)
        self.assertNotIn('12:15', conflict['start_dt'],
                          "UTC time leaked into conflict data")
