# ==============================================================================
# File: apps/core/tests/test_calendar_bound_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Certification for the user-local calendar authority + the
#              calendar-bound truth contract (the class, not one module)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
Calendar-bound truth certification.

Two proven defect shapes, generalized:

  1. **Undated day-claims.** A cached value whose meaning depends on a calendar day,
     stored without recording WHICH day, is correct when written and silently wrong
     after midnight. Write-based staleness cannot see it — *calendar days advance
     without writes* (`docs/WLJ_NUTRITION_STATE_INVESTIGATION.md`).
  2. **Non-user-local dates.** "Today"/"yesterday" resolved from UTC or server time
     are wrong for any user whose local day differs at that instant. At 11 PM Eastern
     it is still today for the user even though UTC has already rolled over.

The registry gate (`CalendarBoundRegistryTests`) is what keeps the class closed: a
module that grows a `*_today` / `daily_*` projection without registering its day stamp
fails CI.
"""
from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone as dj_tz

from apps.core.truth import calendar_day as cal
from apps.users.models import User

# Representative zones spanning UTC offsets, hemispheres and DST behaviours.
ZONES = [
    ("UTC", "UTC"),
    ("Eastern", "America/New_York"),
    ("Central", "America/Chicago"),
    ("Mountain", "America/Denver"),
    ("Pacific", "America/Los_Angeles"),
    ("Hawaii", "Pacific/Honolulu"),          # no DST
    ("Europe", "Europe/London"),
    ("Australia", "Australia/Sydney"),       # southern-hemisphere DST
    ("Asia", "Asia/Kolkata"),                # +05:30 half-hour offset
]


def _user(email, tz_name):
    u = User.objects.create_user(email=email, password="x")
    u.preferences.timezone = tz_name
    u.preferences.save()
    return u


def _at(utc_iso):
    """Freeze `django.utils.timezone.now()` at a UTC instant."""
    return mock.patch.object(
        dj_tz, "now",
        return_value=datetime.fromisoformat(utc_iso).replace(tzinfo=ZoneInfo("UTC")))


class UserLocalCalendarTests(TestCase):
    """The authority resolves the USER's day — never UTC's."""

    def test_utc_midnight_does_not_advance_the_users_today(self):
        """11:00 PM Eastern = 03:00 UTC the NEXT day. It is still today for the user."""
        u = _user("evening@test.com", "America/New_York")
        # 2026-03-10 03:00 UTC == 2026-03-09 23:00 America/New_York
        with _at("2026-03-10T03:00:00"):
            self.assertEqual(cal.today(u), date(2026, 3, 9))
            self.assertEqual(cal.yesterday(u), date(2026, 3, 8))
            self.assertEqual(dj_tz.now().date(), date(2026, 3, 10))  # UTC HAS advanced

    def test_after_local_midnight_the_day_advances_exactly_once(self):
        """12:30 AM Eastern = 04:30 UTC. Now — and only now — today moves."""
        u = _user("after@test.com", "America/New_York")
        with _at("2026-03-10T04:30:00"):
            self.assertEqual(cal.today(u), date(2026, 3, 10))
            self.assertEqual(cal.yesterday(u), date(2026, 3, 9))

    def test_the_boundary_moves_once_and_only_once(self):
        u = _user("once@test.com", "America/New_York")
        seen = []
        for hour in range(20, 24):          # 20:00 → 23:00 UTC on 2026-03-09
            with _at(f"2026-03-09T{hour:02d}:00:00"):
                seen.append(cal.today(u))
        for hour in range(0, 8):            # 00:00 → 07:00 UTC on 2026-03-10
            with _at(f"2026-03-10T{hour:02d}:00:00"):
                seen.append(cal.today(u))
        transitions = sum(1 for a, b in zip(seen, seen[1:]) if a != b)
        self.assertEqual(transitions, 1, seen)

    def test_every_zone_resolves_its_own_day(self):
        """One UTC instant, nine zones — each user gets THEIR calendar day."""
        expected = {
            "UTC": date(2026, 7, 23), "Eastern": date(2026, 7, 22),
            "Central": date(2026, 7, 22), "Mountain": date(2026, 7, 22),
            "Pacific": date(2026, 7, 22), "Hawaii": date(2026, 7, 22),
            "Europe": date(2026, 7, 23), "Australia": date(2026, 7, 23),
            "Asia": date(2026, 7, 23),
        }
        # 2026-07-23 02:00 UTC — the Americas are still on the 22nd.
        with _at("2026-07-23T02:00:00"):
            for label, tz_name in ZONES:
                u = _user(f"zone_{label}@test.com", tz_name)
                self.assertEqual(cal.today(u), expected[label], f"{label} ({tz_name})")

    def test_half_hour_offset_zone(self):
        u = _user("kolkata@test.com", "Asia/Kolkata")     # UTC+05:30
        with _at("2026-07-22T18:45:00"):                  # 00:15 on the 23rd local
            self.assertEqual(cal.today(u), date(2026, 7, 23))

    def test_timezone_name_travels_with_every_answer(self):
        u = _user("tzname@test.com", "Australia/Sydney")
        self.assertEqual(cal.tz_name(u), "Australia/Sydney")
        self.assertEqual(cal.stamp(u)["timezone"], "Australia/Sydney")


class DstAndCalendarEdgeTests(TestCase):
    """DST transitions, leap day and year rollover."""

    def test_spring_forward_day_is_23_hours_local(self):
        """2026-03-08 US spring forward: the local day is 23 hours, and day_bounds
        must express that (end = start of the NEXT local day, never start + 24h)."""
        u = _user("spring@test.com", "America/New_York")
        self.assertEqual(cal.day_length(u, date(2026, 3, 8)), timedelta(hours=23))

    def test_fall_back_day_is_25_hours_local(self):
        u = _user("fall@test.com", "America/New_York")
        self.assertEqual(cal.day_length(u, date(2026, 11, 1)), timedelta(hours=25))

    def test_non_dst_zone_is_always_24_hours(self):
        u = _user("hawaii@test.com", "Pacific/Honolulu")
        for d in (date(2026, 3, 8), date(2026, 11, 1), date(2026, 7, 23)):
            self.assertEqual(cal.day_length(u, d), timedelta(hours=24), d)

    def test_southern_hemisphere_dst(self):
        """Sydney's DST runs opposite to the US — its April transition, not March."""
        u = _user("sydney@test.com", "Australia/Sydney")
        self.assertEqual(cal.day_length(u, date(2026, 4, 5)), timedelta(hours=25))

    def test_day_across_a_dst_boundary_still_resolves(self):
        u = _user("dstday@test.com", "America/New_York")
        # 2026-03-08 07:00 UTC == 02:00 EST → the skipped hour; must not raise.
        with _at("2026-03-08T07:00:00"):
            self.assertEqual(cal.today(u), date(2026, 3, 8))

    def test_leap_day(self):
        u = _user("leap@test.com", "America/Chicago")
        with _at("2028-02-29T18:00:00"):                     # 12:00 local
            self.assertEqual(cal.today(u), date(2028, 2, 29))
            self.assertEqual(cal.yesterday(u), date(2028, 2, 28))
        with _at("2028-03-01T18:00:00"):
            self.assertEqual(cal.yesterday(u), date(2028, 2, 29))

    def test_year_rollover(self):
        u = _user("newyear@test.com", "America/New_York")
        with _at("2027-01-01T04:00:00"):                     # 23:00 Dec 31 local
            self.assertEqual(cal.today(u), date(2026, 12, 31))
        with _at("2027-01-01T06:00:00"):                     # 01:00 Jan 1 local
            self.assertEqual(cal.today(u), date(2027, 1, 1))
            self.assertEqual(cal.yesterday(u), date(2026, 12, 31))


class RelativeExpressionTests(TestCase):
    """Conversational expressions resolve against the USER's calendar."""

    def test_today_and_yesterday_phrases_match_the_user_day(self):
        u = _user("phrase@test.com", "America/Los_Angeles")
        with _at("2026-07-23T04:00:00"):        # 21:00 on the 22nd, Pacific
            self.assertEqual(cal.today(u), date(2026, 7, 22))
            self.assertEqual(cal.resolve(u, "today").start, date(2026, 7, 22))
            self.assertEqual(cal.resolve(u, "yesterday").start, date(2026, 7, 21))

    def test_week_bounds_come_from_the_shared_resolver(self):
        u = _user("week@test.com", "UTC")
        with _at("2026-07-23T12:00:00"):
            start, end = cal.week_bounds(u)
            from apps.core.truth.periods import resolve_period
            p = resolve_period("this_week", date(2026, 7, 23))
            self.assertEqual((start, end), (p.start, p.end))

    def test_unparseable_phrase_is_rejected_not_guessed(self):
        u = _user("bad@test.com", "UTC")
        self.assertIsNone(cal.resolve(u, "sometime around then"))

    def test_part_of_day_is_user_local(self):
        u = _user("daypart@test.com", "America/New_York")
        with _at("2026-07-23T12:00:00"):        # 08:00 Eastern → morning
            self.assertEqual(cal.part_of_day(u), "morning")
        with _at("2026-07-24T02:00:00"):        # 22:00 Eastern → night
            self.assertEqual(cal.part_of_day(u), "night")


class CalendarBoundContractTests(TestCase):
    """The stamp/freshness contract every calendar-bound cached value must satisfy."""

    def setUp(self):
        self.user = _user("contract@test.com", "America/New_York")

    def test_stamp_records_day_timezone_and_authority(self):
        with _at("2026-07-23T03:00:00"):        # 23:00 on the 22nd, Eastern
            s = cal.stamp(self.user)
        self.assertEqual(s["represented_day"], "2026-07-22")
        self.assertEqual(s["timezone"], "America/New_York")
        self.assertEqual(s["authority"], cal.AUTHORITY)
        self.assertIn("generated_at", s)
        self.assertEqual(s["semantics"], "exact_date")

    def test_freshness_current_stale_unknown(self):
        with _at("2026-07-23T16:00:00"):        # 12:00 Eastern on the 23rd
            self.assertEqual(cal.day_freshness(self.user, "2026-07-23")["day_freshness"],
                             cal.CURRENT)
            stale = cal.day_freshness(self.user, "2026-07-22")
            self.assertEqual(stale["day_freshness"], cal.STALE)
            self.assertIn("NOT the user's today", stale["reason"])
            unknown = cal.day_freshness(self.user, None)
            self.assertEqual(unknown["day_freshness"], cal.UNKNOWN)
            self.assertTrue(unknown["reason"])

    def test_freshness_accepts_a_full_stamp_or_a_bare_date(self):
        with _at("2026-07-23T16:00:00"):
            s = cal.stamp(self.user)
            self.assertEqual(cal.day_freshness(self.user, s)["day_freshness"],
                             cal.CURRENT)
            self.assertEqual(
                cal.day_freshness(self.user, s["represented_day"])["day_freshness"],
                cal.CURRENT)

    def test_a_stamp_goes_stale_at_the_users_midnight_not_utcs(self):
        """The whole class in one assertion."""
        with _at("2026-07-23T03:00:00"):        # 23:00 Eastern on the 22nd
            s = cal.stamp(self.user)            # represents 2026-07-22
        with _at("2026-07-23T03:30:00"):        # 23:30 Eastern — UTC already the 23rd
            self.assertEqual(cal.day_freshness(self.user, s)["day_freshness"],
                             cal.CURRENT, "UTC midnight must not stale a user's day")
        with _at("2026-07-23T05:00:00"):        # 01:00 Eastern on the 23rd
            self.assertEqual(cal.day_freshness(self.user, s)["day_freshness"],
                             cal.STALE, "the user's own midnight must stale it")

    def test_is_stale_treats_unknown_as_not_current(self):
        self.assertTrue(cal.is_stale(self.user, None))


class CalendarBoundRegistryTests(TestCase):
    """THE CLASS GATE — a calendar-day claim may not exist in an unregistered module.

    This is what stops the defect returning: adding `foo_today` to a module that does
    not record its represented day fails CI.
    """

    # Field-name shapes that ASSERT a calendar-day quantity.
    import re as _re
    # Includes the INFIX form (`water_today_oz`) — an earlier version missed it,
    # which is exactly how an undated day-claim slips through unnoticed.
    DAY_CLAIM = _re.compile(r"^(daily_|today_|todays_)|_today$|_today_|_yesterday$")
    # Provenance/pointer fields: a timestamp OF something, not a claim ABOUT a day.
    PROVENANCE = _re.compile(r"^last_|_date$|_at$|_ts$|_entry$")

    def test_every_calendar_day_claim_lives_in_a_registered_module(self):
        from apps.core.ai_state.state_builder import get_all_builders
        from apps.core.ai_state.state_freshness import _DATE_BOUND_MODULES
        user = _user("registry@test.com", "UTC")
        offenders = []
        for module, builder in get_all_builders().items():
            try:
                state = builder(user) or {}
            except Exception:
                continue                     # builder needs data it doesn't have here
            if not isinstance(state, dict):
                continue
            claims = [f for f in state
                      if isinstance(f, str) and not f.startswith("_")
                      and self.DAY_CLAIM.search(f) and not self.PROVENANCE.search(f)]
            if claims and module not in _DATE_BOUND_MODULES:
                offenders.append(f"{module}: {sorted(claims)[:6]}")
        self.assertEqual(
            offenders, [],
            "These modules project calendar-day claims but do not record which day "
            "they represent — register them in state_freshness._DATE_BOUND_MODULES "
            "and stamp the builder:\n  " + "\n  ".join(offenders))

    def test_registered_modules_actually_stamp_their_day(self):
        from apps.core.ai_state.state_builder import get_all_builders
        from apps.core.ai_state.state_freshness import _DATE_BOUND_MODULES
        user = _user("stamped@test.com", "America/Denver")
        builders = get_all_builders()
        for module, field in _DATE_BOUND_MODULES.items():
            builder = builders.get(module)
            if builder is None:
                continue
            state = builder(user) or {}
            self.assertIn(field, state,
                          f"{module} is registered as calendar-bound but its builder "
                          f"does not set '{field}'")
            self.assertEqual(state[field], cal.today(user).isoformat(), module)
