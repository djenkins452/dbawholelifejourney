"""Event Frequency capability — the platform primitive (pure, no DB).

Verifies the fourth numeric-truth shape: one deterministic event count per recurring
window, the frequency analytics WLJ owns, and — crucially — that TREND is REUSED (the
series' change() is a HistorySeries.change()) and that a no-data window is UNKNOWN, never
a fabricated zero.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as _tz

from django.test import SimpleTestCase

from apps.core.truth.event_frequency import build_event_frequency_series
from apps.core.truth.reading_window import ReadingWindowSpec
from apps.core.truth.windows import WINDOW_KINDS, daily_windows


@dataclass
class _Row:
    value: float
    at: datetime


_SPEC = ReadingWindowSpec(
    domain="health", metric="glucose", unit="mg/dL",
    value_getter=lambda r: r.value, time_getter=lambda r: r.at,
    low=70.0, high=180.0, urgent_low=54.0, urgent_high=250.0,
)

# A fixed aware "now" so windows are deterministic (no wall-clock dependence).
_NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=_tz.utc)


def _night(days_ago, hour=2):
    """An aware datetime at `hour` on the night `days_ago` days back (in [0,6) → 'night')."""
    d = (_NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0,
                                                  microsecond=0)
    return d


class DailyWindowsTests(SimpleTestCase):
    def test_night_windows_span_each_day_midnight_to_six(self):
        start = (_NOW - timedelta(days=3)).date()
        end = (_NOW - timedelta(days=1)).date()
        wins = daily_windows("night", start, end, _NOW)
        self.assertEqual(len(wins), 3)
        for w in wins:
            self.assertEqual(w.start.hour, 0)
            self.assertEqual(w.end.hour, 6)
            self.assertEqual(w.name, "night")

    def test_future_windows_are_dropped(self):
        # end in the future → those windows never started; only past nights returned.
        start = (_NOW - timedelta(days=1)).date()
        end = (_NOW + timedelta(days=3)).date()
        wins = daily_windows("night", start, end, _NOW)
        for w in wins:
            self.assertLess(w.start, _NOW)

    def test_unknown_kind_returns_empty(self):
        self.assertEqual(daily_windows("nonsense", _NOW.date(), _NOW.date(), _NOW), [])

    def test_all_kinds_resolvable(self):
        for kind in WINDOW_KINDS:
            wins = daily_windows(kind, (_NOW - timedelta(days=2)).date(),
                                 (_NOW - timedelta(days=1)).date(), _NOW)
            self.assertTrue(wins, kind)


class EventFrequencySeriesTests(SimpleTestCase):
    def _windows(self, days):
        start = (_NOW - timedelta(days=days)).date()
        end = (_NOW - timedelta(days=1)).date()
        return daily_windows("night", start, end, _NOW)

    def test_counts_lows_per_night_and_totals(self):
        wins = self._windows(3)                    # nights: -3, -2, -1
        rows = [
            # night -3: one low (65) + one normal
            _Row(120, _night(3, 1)), _Row(65, _night(3, 2)),
            # night -2: two lows (60, 50-severe)
            _Row(60, _night(2, 1)), _Row(50, _night(2, 3)),
            # night -1: three lows (68, 66, 48-severe)
            _Row(68, _night(1, 1)), _Row(66, _night(1, 2)), _Row(48, _night(1, 4)),
        ]
        s = build_event_frequency_series(_SPEC, "low", wins, rows, period_label="night · x")
        d = s.to_dict()
        self.assertTrue(d["present"])
        self.assertEqual(d["windows"], 3)
        self.assertEqual(d["windows_with_data"], 3)
        self.assertEqual([p["count"] for p in d["series"]], [1, 2, 3])
        self.assertEqual(d["total_events"], 6)
        self.assertEqual(d["average_events_per_window"], 2.0)
        self.assertEqual(d["event_rate"], 1.0)     # every measured night had a low
        self.assertEqual(d["highest_window"]["count"], 3)
        self.assertEqual(d["lowest_window"]["count"], 1)

    def test_trend_is_reused_from_history_change(self):
        wins = self._windows(3)
        rows = [
            _Row(120, _night(3, 1)), _Row(65, _night(3, 2)),                 # 1 low
            _Row(60, _night(2, 1)), _Row(50, _night(2, 3)),                 # 2 lows
            _Row(68, _night(1, 1)), _Row(66, _night(1, 2)), _Row(48, _night(1, 4)),  # 3
        ]
        s = build_event_frequency_series(_SPEC, "low", wins, rows)
        change = s.to_dict()["change"]
        self.assertIsNotNone(change)
        self.assertEqual(change["direction"], "rising")        # lows getting MORE frequent
        # Identical to the Trend primitive over the same counts — proves reuse, not a copy.
        self.assertEqual(change, s.to_history_series().change())

    def test_severe_lows_use_urgent_threshold(self):
        wins = self._windows(2)
        rows = [
            _Row(50, _night(2, 2)),                 # night -2: 1 urgent low (<54)
            _Row(60, _night(1, 2)), _Row(48, _night(1, 3)),  # night -1: 1 urgent low (48)
        ]
        s = build_event_frequency_series(_SPEC, "urgent_low", wins, rows)
        d = s.to_dict()
        self.assertEqual(d["total_events"], 2)     # 50 and 48; the 60 is not urgent
        self.assertEqual([p["count"] for p in d["series"]], [1, 1])

    def test_by_hour_clusters_the_events(self):
        wins = self._windows(2)
        rows = [_Row(50, _night(2, 3)), _Row(48, _night(1, 3))]   # both at 03:00
        s = build_event_frequency_series(_SPEC, "low", wins, rows)
        by_hour = s.to_dict()["by_hour"]
        self.assertEqual(by_hour["peak_hour"], 3)

    def test_zero_events_on_measured_nights_is_real_not_empty(self):
        wins = self._windows(2)
        rows = [_Row(120, _night(2, 2)), _Row(110, _night(1, 2))]   # data, but no lows
        s = build_event_frequency_series(_SPEC, "low", wins, rows)
        d = s.to_dict()
        self.assertTrue(d["present"])              # we DID measure — a real "no lows"
        self.assertEqual(d["total_events"], 0)
        self.assertEqual(d["event_rate"], 0.0)

    def test_no_data_windows_are_unknown_not_zero(self):
        wins = self._windows(3)
        rows = []                                  # nothing recorded at all
        s = build_event_frequency_series(_SPEC, "low", wins, rows)
        d = s.to_dict()
        self.assertFalse(d["present"])             # honest empty, never "0 lows"
        self.assertEqual(d["windows_with_data"], 0)

    def test_no_data_nights_do_not_fake_a_downward_trend(self):
        # Two measured nights (both 2 lows) then a gap of unmeasured nights. The trend must
        # be FLAT over the measured nights, not "falling" because of no-data zeros.
        start = (_NOW - timedelta(days=6)).date()
        end = (_NOW - timedelta(days=1)).date()
        wins = daily_windows("night", start, end, _NOW)
        rows = [
            _Row(60, _night(6, 2)), _Row(50, _night(6, 3)),      # night -6: 2 lows
            _Row(65, _night(5, 2)), _Row(48, _night(5, 3)),      # night -5: 2 lows
        ]  # nights -4..-1 have NO data
        s = build_event_frequency_series(_SPEC, "low", wins, rows)
        d = s.to_dict()
        self.assertEqual(d["windows_with_data"], 2)
        self.assertEqual(d["change"]["direction"], "flat")

    def test_unknown_event_without_threshold_returns_none(self):
        spec = ReadingWindowSpec(
            domain="x", metric="y", unit="u",
            value_getter=lambda r: r.value, time_getter=lambda r: r.at,
            low=70.0, high=180.0)          # no urgent_low threshold
        wins = self._windows(1)
        self.assertIsNone(
            build_event_frequency_series(spec, "urgent_low", wins, [_Row(50, _night(1))]))
