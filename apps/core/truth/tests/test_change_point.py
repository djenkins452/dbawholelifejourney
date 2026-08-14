"""Change-Point Detection platform capability — pure-math invariant tests.

Tests the INVARIANT, not the implementation: a real trend shift is found near the true
location, ordinary noise / a single trend does NOT manufacture one, too few points are
honest, endpoints can't trivially become change points, dates (not indices) drive the
math, and the same input always yields the same output.
"""
from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.core.truth.change_point import detect_change_point

_D0 = date(2026, 1, 1)


def _series(values, *, step_days=1, start=_D0):
    return [(start + timedelta(days=i * step_days), v) for i, v in enumerate(values)]


def _wiggle(values, amp=0.2):
    """Add a fixed, deterministic ±amp zigzag so a series looks like real (noisy) data
    without any randomness."""
    return [v + (amp if i % 2 else -amp) for i, v in enumerate(values)]


class ChangePointDetectionTests(SimpleTestCase):
    def test_clear_reversal_is_detected_near_the_kink(self):
        # 15 days falling (280→266), then 15 days rising (266→280). Kink at index 15.
        down = [280 - i for i in range(15)]
        up = [266 + i for i in range(15)]
        r = detect_change_point(_series(_wiggle(down + up)), metric="weight")
        self.assertTrue(r["supported"])
        cp = date.fromisoformat(r["change_date"])
        self.assertLessEqual(abs((cp - (_D0 + timedelta(days=15))).days), 2)
        self.assertEqual(r["pre_change"]["direction"], "falling")
        self.assertEqual(r["post_change"]["direction"], "rising")
        self.assertGreaterEqual(r["residual_reduction"], 0.5)

    def test_acceleration_is_detected(self):
        # slow decline (-0.2/day) then steep decline (-1.5/day).
        slow = [300 - 0.2 * i for i in range(14)]
        fast = [slow[-1] - 1.5 * (i + 1) for i in range(14)]
        r = detect_change_point(_series(_wiggle(slow + fast, amp=0.1)), metric="weight")
        self.assertTrue(r["supported"])
        self.assertEqual(r["pre_change"]["direction"], "falling")
        self.assertEqual(r["post_change"]["direction"], "falling")
        # the post slope is markedly steeper (more negative) than the pre slope.
        self.assertLess(r["post_change"]["slope_per_day"], r["pre_change"]["slope_per_day"])

    def test_single_trend_has_no_supported_change(self):
        steady = [280 - 0.3 * i for i in range(30)]        # one clean slope
        r = detect_change_point(_series(_wiggle(steady)), metric="weight")
        self.assertFalse(r["supported"])
        self.assertIn("overall", r)
        self.assertEqual(r["overall"]["direction"], "falling")

    def test_noise_around_flat_is_not_a_change(self):
        # A flat line with a deterministic sawtooth — no underlying trend change.
        base = [200 for _ in range(30)]
        noisy = [v + (1.5 if i % 3 == 0 else -1.2 if i % 3 == 1 else 0.4)
                 for i, v in enumerate(base)]
        r = detect_change_point(_series(noisy), metric="weight")
        self.assertFalse(r["supported"])

    def test_insufficient_observations_is_honest(self):
        r = detect_change_point(_series([280, 279, 278, 277, 276]), metric="weight")
        self.assertFalse(r["supported"])
        self.assertEqual(r["observations"], 5)
        self.assertIn("at least", r["reason"])

    def test_empty_is_present_false(self):
        r = detect_change_point([], metric="weight")
        self.assertFalse(r["present"])
        self.assertFalse(r["supported"])
        self.assertEqual(r["observations"], 0)

    def test_single_endpoint_outlier_is_not_a_change_point(self):
        # A clean flat series with ONE wild first value. The outlier must not become a
        # change point (endpoint exclusion + segment guards).
        vals = [260] + [280 - 0.05 * i for i in range(20)]
        r = detect_change_point(_series(_wiggle(vals)), metric="weight")
        if r["supported"]:
            cp = date.fromisoformat(r["change_date"])
            self.assertGreater((cp - _D0).days, 3)          # never the first point
        # (either unsupported, or a change well away from the outlier — both acceptable)

    def test_uses_actual_dates_not_indices(self):
        # Same values, but the second half is sampled sparsely (every 3 days). The change
        # date must reflect real calendar time, not the observation index.
        down = [280 - i for i in range(12)]
        up = [268 + i for i in range(12)]
        pts = _series(down) + _series(up, step_days=3,
                                      start=_D0 + timedelta(days=12))
        r = detect_change_point(pts, metric="weight")
        self.assertTrue(r["supported"])
        # pre-segment spans ~11 days, post-segment spans ~33 days — day-aware.
        self.assertGreater(r["post_change"]["span_days"], r["pre_change"]["span_days"])

    def test_deterministic(self):
        vals = _wiggle([280 - i for i in range(15)] + [265 + i for i in range(15)])
        self.assertEqual(detect_change_point(_series(vals), metric="weight"),
                         detect_change_point(_series(vals), metric="weight"))

    def test_weak_change_below_threshold_is_unsupported(self):
        # Two nearly-identical slopes (-0.30 then -0.34). The tiny kink does not clear the
        # residual-reduction bar → no supported change point (not the "best" weak split).
        a = [280 - 0.30 * i for i in range(15)]
        b = [a[-1] - 0.34 * (i + 1) for i in range(15)]
        r = detect_change_point(_series(_wiggle(a + b)), metric="weight",
                                min_residual_reduction=0.50)
        self.assertFalse(r["supported"])

    def test_residual_reduction_is_a_concrete_statistic_not_a_label(self):
        r = detect_change_point(
            _series(_wiggle([280 - i for i in range(15)] + [265 + i for i in range(15)])),
            metric="weight")
        self.assertIn("residual_reduction", r)
        self.assertIsInstance(r["residual_reduction"], float)
        self.assertNotIn("confidence", r)                   # no vague heuristic label
