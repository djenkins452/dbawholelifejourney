"""Tests for the reusable READING-WINDOW series producer (apps.core.truth.reading_window).

Pure statistics over injected rows — no DB, no domain coupling. A row here is just a
tiny object with `.v` and `.t`; the spec's getters read them. Proves the platform math
(min/max/avg, in-range, below/above, urgent, excursions, sample cap) independent of any
metric — the guarantee that heart rate / SpO2 / BP adopt the same producer correctly.
"""
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.core.truth.reading_window import (
    ReadingWindowSpec,
    build_reading_series,
)
from apps.core.truth.windows import Window


NOW = datetime(2026, 7, 29, 6, 0, tzinfo=timezone.utc)
WIN = Window("test", NOW - timedelta(hours=6), NOW, "the last 6 hours")


class _Row:
    def __init__(self, v, minutes_before):
        self.v = v
        self.t = NOW - timedelta(minutes=minutes_before)


SPEC = ReadingWindowSpec(
    domain="test", metric="metric", unit="u",
    value_getter=lambda r: r.v, time_getter=lambda r: r.t,
    low=70, high=180, urgent_low=54, urgent_high=250,
)


def _rows(values_newest_first):
    # values listed newest-first; assign descending minutes so time is ascending overall
    n = len(values_newest_first)
    return [_Row(v, minutes_before=(i + 1) * 5)
            for i, v in enumerate(values_newest_first)]


class ReadingSeriesStatsTests(SimpleTestCase):
    def test_empty_rows(self):
        s = build_reading_series(SPEC, WIN, []).to_dict()
        self.assertFalse(s["present"])
        self.assertEqual(s["count"], 0)
        self.assertIsNone(s["minimum"])
        self.assertEqual(s["low_excursions"], [])

    def test_basic_aggregates(self):
        s = build_reading_series(SPEC, WIN, _rows([100, 90, 80])).to_dict()
        self.assertTrue(s["present"])
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["minimum"], 80)
        self.assertEqual(s["maximum"], 100)
        self.assertEqual(s["average"], 90)

    def test_in_range_below_above_counts(self):
        # 65 low, 75/120/175 in-range, 210 high
        s = build_reading_series(SPEC, WIN, _rows([65, 75, 120, 175, 210])).to_dict()
        self.assertEqual(s["below_low"], 1)
        self.assertEqual(s["in_range"], 3)
        self.assertEqual(s["above_high"], 1)
        self.assertEqual(s["in_range_pct"], 60.0)
        self.assertEqual(s["below_low_pct"], 20.0)

    def test_urgent_low_counts_severe_only(self):
        s = build_reading_series(SPEC, WIN, _rows([41, 50, 68, 120])).to_dict()
        self.assertEqual(s["below_low"], 3)        # 41, 50, 68 all < 70
        self.assertEqual(s["urgent_low_count"], 2)  # 41, 50 < 54

    def test_low_excursions_are_worst_first_with_timestamps(self):
        s = build_reading_series(SPEC, WIN, _rows([68, 41, 55, 120])).to_dict()
        vals = [e["value"] for e in s["low_excursions"]]
        self.assertEqual(vals, [41, 55, 68])       # severity order, not chronological
        for e in s["low_excursions"]:
            self.assertIn("at", e)                 # each carries its timestamp

    def test_first_and_last_are_chronological(self):
        s = build_reading_series(SPEC, WIN, _rows([120, 110, 100])).to_dict()
        # rows() makes newest-first values map to ascending time, so oldest value = 100
        self.assertEqual(s["first"]["value"], 100)
        self.assertEqual(s["last"]["value"], 120)

    def test_sample_cap_truncates_but_stats_cover_all(self):
        rows = _rows([100] * 300)
        s = build_reading_series(SPEC, WIN, rows, sample_cap=50).to_dict()
        self.assertEqual(s["count"], 300)          # stats over ALL rows
        self.assertTrue(s["samples_truncated"])
        self.assertEqual(len(s["samples"]), 50)    # serialization bounded

    def test_thresholds_none_disables_range_stats(self):
        spec = ReadingWindowSpec(
            domain="t", metric="m", unit="u",
            value_getter=lambda r: r.v, time_getter=lambda r: r.t)
        s = build_reading_series(spec, WIN, _rows([10, 20, 30])).to_dict()
        self.assertIsNone(s["in_range"])
        self.assertIsNone(s["below_low"])
        self.assertEqual(s["low_excursions"], [])
