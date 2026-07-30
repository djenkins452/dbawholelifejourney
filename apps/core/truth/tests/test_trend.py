"""Tests for the deterministic TREND primitive on HistorySeries (apps.core.truth.history).

Pure — no DB. Builds a HistorySeries from synthetic points and asserts the `change`
block (delta, pct, slope, direction). This is the reusable trend every history metric
now carries; the closed ratchet defects (weight_30_day_change, sleep_trend) are
projections of exactly this.
"""
from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.core.truth.history import HistoryPoint, HistorySeries, series_from_rows
from apps.core.truth.periods import Period


def _series(values, metric="m"):
    start = date(2026, 7, 1)
    rows = [{"date": start + timedelta(days=i), "value": v}
            for i, v in enumerate(values)]
    p = Period("custom", start, start + timedelta(days=len(values) - 1), "window")
    return series_from_rows("health", metric, p, rows, unit="u")


class TrendTests(SimpleTestCase):
    def test_none_with_fewer_than_two_points(self):
        self.assertIsNone(_series([]).change())
        self.assertIsNone(_series([100]).change())

    def test_rising(self):
        ch = _series([100, 110, 120, 130]).change()
        self.assertEqual(ch["direction"], "rising")
        self.assertEqual(ch["first"], 100)
        self.assertEqual(ch["last"], 130)
        self.assertEqual(ch["delta"], 30)
        self.assertEqual(ch["pct_change"], 30.0)
        self.assertGreater(ch["slope_per_point"], 0)

    def test_falling(self):
        ch = _series([300, 295, 290, 285]).change()
        self.assertEqual(ch["direction"], "falling")
        self.assertEqual(ch["delta"], -15)
        self.assertLess(ch["slope_per_point"], 0)

    def test_flat_within_band(self):
        # 200 -> 200.5 is < 0.5% of magnitude → flat
        ch = _series([200, 201, 199, 200.5]).change()
        self.assertEqual(ch["direction"], "flat")

    def test_direction_is_arithmetic_not_a_verdict(self):
        # falling glucose and falling weight both report "falling" — desirability is the
        # model's to judge, WLJ never says improving/worsening.
        self.assertEqual(_series([180, 120]).change()["direction"], "falling")

    def test_change_present_in_to_dict(self):
        d = _series([10, 20, 30]).to_dict()
        self.assertIn("change", d)
        self.assertEqual(d["change"]["direction"], "rising")

    def test_to_dict_change_none_for_single_point(self):
        self.assertIsNone(_series([42]).to_dict()["change"])

    def test_pct_change_handles_zero_first(self):
        ch = _series([0, 5, 10]).change()
        self.assertIsNone(ch["pct_change"])      # undefined vs a zero baseline
        self.assertEqual(ch["direction"], "rising")
