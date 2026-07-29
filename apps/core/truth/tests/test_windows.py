"""Tests for the intra-day TIME-WINDOW resolver (apps.core.truth.windows).

Pure datetime math — no DB. Every window is measured against a FIXED aware `now` so
the assertions are deterministic regardless of when the suite runs.
"""
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.core.truth.periods import resolve_date_expression
from apps.core.truth.windows import (
    MAX_WINDOW_HOURS,
    resolve_window,
    window_from_period,
)


# A fixed reference "now": 2026-07-29 11:00 UTC (a Wednesday).
NOW = datetime(2026, 7, 29, 11, 0, tzinfo=timezone.utc)


class ResolveWindowTests(SimpleTestCase):
    def test_unparseable_returns_none(self):
        self.assertIsNone(resolve_window("the vibes", NOW))
        self.assertIsNone(resolve_window("", NOW))
        self.assertIsNone(resolve_window(None, NOW))

    def test_day_phrase_is_not_this_resolvers_job(self):
        # "last Tuesday" / "July 4" belong to periods.py — resolve_window returns None
        # so the caller can fall back. (window_from_period handles the widening.)
        self.assertIsNone(resolve_window("last Tuesday", NOW))
        self.assertIsNone(resolve_window("July 4", NOW))

    def test_overnight_is_midnight_to_six_am(self):
        w = resolve_window("overnight", NOW)
        self.assertIsNotNone(w)
        self.assertEqual(w.start, datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(w.end, datetime(2026, 7, 29, 6, 0, tzinfo=timezone.utc))

    def test_last_night_alias(self):
        self.assertEqual(resolve_window("last night", NOW).start,
                         resolve_window("overnight", NOW).start)

    def test_overnight_during_the_night_clamps_end_to_now(self):
        early = datetime(2026, 7, 29, 3, 30, tzinfo=timezone.utc)
        w = resolve_window("overnight", early)
        self.assertEqual(w.end, early)          # not 6 AM (which is in the future)

    def test_since_midnight_is_midnight_to_now(self):
        w = resolve_window("since midnight", NOW)
        self.assertEqual(w.start, datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(w.end, NOW)
        self.assertEqual(resolve_window("today", NOW).start, w.start)

    def test_past_n_hours(self):
        w = resolve_window("past 12 hours", NOW)
        self.assertEqual(w.start, NOW - timedelta(hours=12))
        self.assertEqual(w.end, NOW)
        self.assertAlmostEqual(w.hours(), 12.0, places=3)

    def test_last_hour_singular(self):
        w = resolve_window("last hour", NOW)
        self.assertAlmostEqual(w.hours(), 1.0, places=3)

    def test_word_number_hours(self):
        w = resolve_window("past six hours", NOW)
        self.assertAlmostEqual(w.hours(), 6.0, places=3)

    def test_hours_shorthand(self):
        self.assertAlmostEqual(resolve_window("24h", NOW).hours(), 24.0, places=3)

    def test_this_morning_clamped_to_noon(self):
        w = resolve_window("this morning", NOW)   # now is 11:00 → end is now
        self.assertEqual(w.start, datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(w.end, NOW)

    def test_yesterday_full_local_day(self):
        w = resolve_window("yesterday", NOW)
        self.assertEqual(w.start, datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(w.end, datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc))

    def test_huge_hour_request_is_clamped_and_flagged(self):
        w = resolve_window("past 1000 hours", NOW)
        self.assertTrue(w.clamped)
        self.assertAlmostEqual(w.hours(), MAX_WINDOW_HOURS, places=3)


class WindowFromPeriodTests(SimpleTestCase):
    def test_widens_a_past_day_to_a_full_window(self):
        p = resolve_date_expression("yesterday", NOW.date())
        w = window_from_period(p, NOW)
        self.assertEqual(w.start, datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc))
        # end is start-of-next-day (exclusive upper bound for a full day)
        self.assertEqual(w.end, datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc))

    def test_today_period_clamped_to_now(self):
        p = resolve_date_expression("today", NOW.date())
        w = window_from_period(p, NOW)
        self.assertEqual(w.end, NOW)
