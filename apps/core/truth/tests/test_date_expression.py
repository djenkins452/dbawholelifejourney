# ==============================================================================
# File: apps/core/truth/tests/test_date_expression.py
# Description: The shared conversational date-phrase resolver (resolve_date_expression)
#              — one deterministic authority resolves today/yesterday/last Tuesday/
#              July 4/last week BEFORE any domain provider sees the phrase.
# ==============================================================================
from datetime import date

from django.test import SimpleTestCase

from apps.core.truth.periods import resolve_date_expression

# A fixed, known "today": Sunday, 2026-07-19.
TODAY = date(2026, 7, 19)


class ResolveDateExpressionTests(SimpleTestCase):
    def _one(self, phrase):
        p = resolve_date_expression(phrase, TODAY)
        self.assertIsNotNone(p, f"{phrase!r} did not resolve")
        self.assertEqual(p.start, p.end, f"{phrase!r} is not a single day")
        return p.start

    def test_today_yesterday(self):
        self.assertEqual(self._one("today"), date(2026, 7, 19))
        self.assertEqual(self._one("yesterday"), date(2026, 7, 18))

    def test_last_weekday_is_most_recent_past(self):
        self.assertEqual(self._one("last Tuesday"), date(2026, 7, 14))
        self.assertEqual(self._one("Tuesday"), date(2026, 7, 14))  # bare = on/before

    def test_this_and_next_weekday(self):
        self.assertEqual(self._one("this Friday"), date(2026, 7, 17))
        self.assertEqual(self._one("next Monday"), date(2026, 7, 20))

    def test_explicit_month_day(self):
        self.assertEqual(self._one("July 4"), date(2026, 7, 4))
        self.assertEqual(self._one("July 4th"), date(2026, 7, 4))
        self.assertEqual(self._one("Jul 4 2025"), date(2025, 7, 4))
        self.assertEqual(self._one("7/4"), date(2026, 7, 4))

    def test_yearless_future_rolls_back_to_most_recent(self):
        # December has not happened yet in July → most recent past = last year.
        self.assertEqual(self._one("December 25"), date(2025, 12, 25))

    def test_iso_passthrough(self):
        self.assertEqual(self._one("2026-04-07"), date(2026, 4, 7))

    def test_named_ranges_stay_ranges(self):
        p = resolve_date_expression("last week", TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 7, 6), date(2026, 7, 12)))
        p = resolve_date_expression("last month", TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 6, 1), date(2026, 6, 30)))

    def test_unparseable_is_none_not_error(self):
        self.assertIsNone(resolve_date_expression("whenever-ish", TODAY))
        self.assertIsNone(resolve_date_expression("", TODAY))
        self.assertIsNone(resolve_date_expression(None, TODAY))
