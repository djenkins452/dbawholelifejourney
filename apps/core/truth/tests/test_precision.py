"""Tests for the reusable timestamp-precision truth model (apps/core/truth/precision.py).

The whole point of this module is that WLJ never claims more precision than a source
carries, and never fabricates a FUTURE instant to store a date-only value.
"""
from __future__ import annotations

import datetime as _dt

from django.test import TestCase
from django.utils import timezone

from apps.core.truth.precision import (
    Precision, infer_precision, resolve_instant, format_instant,
)


class PrecisionVocabularyTests(TestCase):
    def test_order_fine_to_coarse(self):
        self.assertLess(Precision.rank(Precision.SECOND), Precision.rank(Precision.DAY))
        self.assertLess(Precision.rank(Precision.DAY), Precision.rank(Precision.YEAR))
        # UNKNOWN is the coarsest (least trustworthy).
        self.assertEqual(Precision.rank(Precision.UNKNOWN), len(Precision.ORDER) - 1)

    def test_coarser_picks_the_weaker(self):
        self.assertEqual(Precision.coarser(Precision.SECOND, Precision.DAY), Precision.DAY)
        self.assertEqual(Precision.coarser(Precision.YEAR, Precision.MINUTE), Precision.YEAR)

    def test_is_subday(self):
        self.assertTrue(Precision.is_subday(Precision.MINUTE))
        self.assertFalse(Precision.is_subday(Precision.DAY))


class InferPrecisionTests(TestCase):
    def test_from_python_types(self):
        self.assertEqual(infer_precision(None), Precision.UNKNOWN)
        self.assertEqual(infer_precision(_dt.date(2026, 7, 20)), Precision.DAY)
        self.assertEqual(infer_precision(_dt.datetime(2026, 7, 20, 5, 54)), Precision.SECOND)

    def test_from_iso_strings(self):
        self.assertEqual(infer_precision("2026"), Precision.YEAR)
        self.assertEqual(infer_precision("2026-07"), Precision.MONTH)
        self.assertEqual(infer_precision("2026-07-20"), Precision.DAY)
        self.assertEqual(infer_precision("2026-07-20T05:54"), Precision.MINUTE)
        self.assertEqual(infer_precision("2026-07-20T05:54:13"), Precision.SECOND)
        self.assertEqual(infer_precision("2026-07-20T05:54:13Z"), Precision.SECOND)
        self.assertEqual(infer_precision("not a date"), Precision.UNKNOWN)


class ResolveInstantTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_real_instant_preserved_verbatim(self):
        dt = self.now - _dt.timedelta(hours=3)
        inst, prec = resolve_instant(dt, now=self.now)
        self.assertEqual(inst, dt)
        self.assertEqual(prec, Precision.SECOND)

    def test_iso_instant_string_is_a_real_time(self):
        inst, prec = resolve_instant("2020-01-02T08:30:00+00:00", now=self.now)
        self.assertEqual(prec, Precision.SECOND)
        self.assertEqual(inst.year, 2020)
        self.assertEqual(timezone.localtime(inst).hour if timezone.is_aware(inst) else inst.hour, 8)

    def test_date_only_is_day_precision_and_never_future(self):
        # A date-only value for TODAY must never be stored in the future, and it is
        # reported as DAY precision so the fabricated sub-day part is never trusted.
        today = timezone.localdate(self.now)
        inst, prec = resolve_instant(today, now=self.now)
        self.assertEqual(prec, Precision.DAY)
        self.assertLessEqual(inst, self.now)

    def test_date_only_before_noon_clamps_to_now(self):
        # Simulate the incident: now = 06:12, date-only today → noon would be future.
        six_am = timezone.make_aware(
            _dt.datetime.combine(timezone.localdate(), _dt.time(6, 12))
        )
        inst, prec = resolve_instant(timezone.localdate(), now=six_am)
        self.assertEqual(prec, Precision.DAY)
        self.assertEqual(inst, six_am)  # clamped, not future noon

    def test_past_date_uses_noon_not_future(self):
        past = timezone.localdate(self.now) - _dt.timedelta(days=5)
        inst, prec = resolve_instant(past, now=self.now)
        self.assertEqual(prec, Precision.DAY)
        self.assertEqual(timezone.localtime(inst).hour, 12)  # noon of a past day is fine

    def test_month_and_year_precision(self):
        i_m, p_m = resolve_instant("2020-03", now=self.now)
        self.assertEqual(p_m, Precision.MONTH)
        self.assertEqual((i_m.year, i_m.month), (2020, 3))
        i_y, p_y = resolve_instant("2019", now=self.now)
        self.assertEqual(p_y, Precision.YEAR)
        self.assertEqual(i_y.year, 2019)

    def test_unknown_without_fallback_is_none(self):
        inst, prec = resolve_instant(None, now=self.now)
        self.assertIsNone(inst)
        self.assertEqual(prec, Precision.UNKNOWN)

    def test_fallback_date_used_when_value_has_none(self):
        fb = timezone.localdate(self.now) - _dt.timedelta(days=2)
        inst, prec = resolve_instant(None, fallback_date=fb, now=self.now)
        self.assertEqual(prec, Precision.DAY)
        self.assertEqual(timezone.localtime(inst).date(), fb)


class FormatInstantTests(TestCase):
    def setUp(self):
        self.now = timezone.make_aware(_dt.datetime(2026, 7, 20, 15, 0))

    def test_day_precision_never_shows_a_clock_time(self):
        inst, _ = resolve_instant(timezone.localdate(self.now), now=self.now)
        out = format_instant(inst, Precision.DAY, now=self.now)
        self.assertEqual(out, "Today")
        self.assertNotIn(":", out)  # the whole point — no fabricated 12:00 PM

    def test_day_precision_relative_and_absolute(self):
        y = self.now - _dt.timedelta(days=1)
        self.assertEqual(format_instant(y, Precision.DAY, now=self.now), "Yesterday")
        old = timezone.make_aware(_dt.datetime(2025, 3, 4, 9, 0))
        self.assertEqual(format_instant(old, Precision.DAY, now=self.now), "March 4, 2025")

    def test_minute_precision_shows_time(self):
        dt = timezone.make_aware(_dt.datetime(2026, 7, 20, 5, 54))
        out = format_instant(dt, Precision.MINUTE, now=self.now)
        self.assertIn("Today", out)
        self.assertIn("5:54", out)

    def test_month_and_year(self):
        dt = timezone.make_aware(_dt.datetime(2026, 7, 1, 12, 0))
        self.assertEqual(format_instant(dt, Precision.MONTH, now=self.now), "July 2026")
        self.assertEqual(format_instant(dt, Precision.YEAR, now=self.now), "2026")

    def test_unknown_is_honest(self):
        self.assertEqual(format_instant(None, Precision.UNKNOWN, now=self.now), "date unknown")
