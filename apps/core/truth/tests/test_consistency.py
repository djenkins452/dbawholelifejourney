"""Consistency / Regularity platform capability — pure-math invariant tests.

Tests the INVARIANT, not the implementation: circular (clock) statistics are midnight-safe,
linear statistics are ordinary, missing/insufficient observations are honest (empty ≠ zero
variance), the variability change is arithmetic, and the same observations always produce
the same dict.
"""
from datetime import date

from django.test import SimpleTestCase

from apps.core.truth.consistency import (
    ConsistencyMetric,
    circular_diff_minutes,
    circular_stats,
)


def _clock(values):
    return ConsistencyMetric("sleep", "bedtime", "clock", "minutes",
                             tuple((date(2026, 8, 1 + i), float(v))
                                   for i, v in enumerate(values)))


def _linear(values):
    return ConsistencyMetric("sleep", "duration", "linear", "minutes",
                             tuple((date(2026, 8, 1 + i), float(v))
                                   for i, v in enumerate(values)))


class CircularMathTests(SimpleTestCase):
    def test_circular_diff_is_shortest_arc(self):
        self.assertEqual(circular_diff_minutes(1430, 10), 20)     # 11:50 PM ↔ 12:10 AM
        self.assertEqual(circular_diff_minutes(10, 1430), 20)     # symmetric
        self.assertEqual(circular_diff_minutes(0, 720), 720)      # antipodal = max
        self.assertEqual(circular_diff_minutes(600, 600), 0)      # identical

    def test_midnight_crossing_is_tight_not_a_full_day(self):
        # 11:45 PM, 12:05 AM, 11:55 PM, 12:10 AM — all within ~25 min of midnight.
        m = _clock([1425, 5, 1435, 10]).to_dict()
        # Circular std must be small (minutes), NOT the ~700+ a naive linear var would give.
        self.assertLess(m["std_dev"], 30)
        self.assertLessEqual(m["max_deviation"], 30)
        # Typical time sits around midnight, never noon.
        self.assertIn(m["typical_time"].split(":")[0], ("11", "12"))

    def test_naive_linear_would_be_wrong_here(self):
        # Sanity: the same values under LINEAR stats would explode — proving the circular
        # treatment is load-bearing, not decorative.
        vals = [1425.0, 5.0, 1435.0, 10.0]
        mean = sum(vals) / len(vals)
        linear_std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        self.assertGreater(linear_std, 600)                       # the trap
        self.assertLess(_clock(vals).to_dict()["std_dev"], 30)    # avoided


class ConsistencyMetricTests(SimpleTestCase):
    def test_perfectly_consistent_has_zero_spread(self):
        m = _clock([1380, 1380, 1380, 1380]).to_dict()            # 11:00 PM every night
        self.assertEqual(m["std_dev"], 0.0)
        self.assertEqual(m["mean_abs_deviation"], 0.0)
        self.assertEqual(m["typical_time"], "11:00 PM")

    def test_highly_variable_has_large_spread(self):
        # 8 PM, 11 PM, 2 AM, 10 PM — a swinging schedule.
        m = _clock([1200, 1380, 120, 1320]).to_dict()
        self.assertGreater(m["std_dev"], 90)

    def test_linear_duration_uses_ordinary_stats(self):
        m = _linear([400, 460, 420, 480]).to_dict()               # minutes asleep
        self.assertEqual(m["kind"], "linear")
        self.assertAlmostEqual(m["mean"], 440.0, places=1)
        self.assertGreater(m["std_dev"], 0)
        self.assertNotIn("typical_time", m)                       # clock-only field absent

    def test_insufficient_and_missing_are_honest_not_zero(self):
        self.assertFalse(_clock([]).to_dict()["present"])         # no data ≠ present
        self.assertEqual(_clock([]).to_dict()["observations"], 0)
        one = _clock([1380]).to_dict()
        self.assertFalse(one["present"])                          # one point = no spread
        self.assertEqual(one["observations"], 1)
        self.assertNotIn("std_dev", one)                          # never a fabricated 0.0

    def test_most_and_least_regular(self):
        # nights: 11:00, 11:05, 11:00, 2:00 AM (the outlier).
        m = _clock([1380, 1385, 1380, 120]).to_dict()
        self.assertEqual(m["least_regular"]["date"], "2026-08-04")   # the 2 AM night
        self.assertNotEqual(m["most_regular"]["date"], "2026-08-04")  # not the outlier
        self.assertGreater(m["least_regular"]["deviation"],
                           m["most_regular"]["deviation"])

    def test_deterministic_reproducibility(self):
        vals = [1380, 1400, 1360, 1390, 1370, 1410]
        self.assertEqual(_clock(vals).to_dict(), _clock(vals).to_dict())

    def test_observations_series_carries_dates_and_clock(self):
        m = _clock([1380, 1385]).to_dict()
        s = m["observations_series"]
        self.assertEqual(len(s), 2)
        self.assertIn("date", s[0])
        self.assertIn("clock", s[0])                              # human-readable time
        self.assertIn("deviation_minutes", s[0])


class VariabilityChangeTests(SimpleTestCase):
    def test_becoming_more_regular_falls(self):
        # first half swings widely, second half tightens → spread FALLING (more regular).
        m = _clock([1200, 60, 1320, 1380, 1385, 1382]).to_dict()
        vc = m["variability_change"]
        self.assertEqual(vc["direction"], "falling")
        self.assertLess(vc["last_half_std"], vc["first_half_std"])

    def test_becoming_less_regular_rises(self):
        m = _clock([1380, 1385, 1382, 1200, 60, 1320]).to_dict()
        vc = m["variability_change"]
        self.assertEqual(vc["direction"], "rising")

    def test_stable_spread_is_flat(self):
        m = _clock([1380, 1390, 1382, 1388, 1381, 1389]).to_dict()
        self.assertEqual(m["variability_change"]["direction"], "flat")

    def test_too_few_observations_no_change(self):
        self.assertIsNone(_clock([1380, 1385, 1382]).to_dict()["variability_change"])


class CircularStatsTests(SimpleTestCase):
    def test_empty_is_none(self):
        self.assertIsNone(circular_stats([]))

    def test_resultant_reflects_concentration(self):
        tight = circular_stats([1380, 1381, 1379])
        spread = circular_stats([0, 480, 960])                   # evenly around the clock
        self.assertGreater(tight["resultant"], 0.99)
        self.assertLess(spread["resultant"], 0.1)
