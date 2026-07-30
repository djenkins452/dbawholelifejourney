"""
Platform capability: EVENT FREQUENCY SERIES (how often an event happens over time).

The fourth shape of Layer-1 numeric truth, alongside:
    * CURRENT   — the single "now" scalar (CurrentTruth)
    * HISTORY   — a per-DAY aggregate trend over a Period (HistorySeries)
    * READINGS  — the individual samples inside ONE datetime Window (ReadingSeries)
    * FREQUENCY — the COUNT of a named EVENT across a SERIES of recurring windows ← THIS

READINGS answers "what were my lows overnight" for one night. It cannot answer "are my
overnight lows becoming MORE FREQUENT" — that needs the low COUNT for each of many
nights, compared over time. HISTORY collapses a day into one mean, so a night's low
count is invisible to it, and COMPARISON compares averages/totals, not excursion counts.
`EventFrequencySeries` is that missing shape: one deterministic event count per recurring
window (each night / each day / each morning …), plus the frequency analytics a person
actually asks about.

DOMAIN-AGNOSTIC BY CONSTRUCTION and REUSE-ONLY:
    * the per-window COUNT is `build_reading_series(...)` — the exact reading-window stats
      engine, never a new counter;
    * the event THRESHOLD is `event_predicate(spec, event)` — the exact reading-window
      thresholds, never re-derived;
    * the TREND over the series is a `HistorySeries.change()` — the exact Trend primitive,
      never a duplicated slope/direction. Trend simply CONSUMES this series.
This module owns ONLY the frequency-specific analytics Trend does not: total_events,
average_events_per_window, event_rate, windows_with_event, highest/lowest window, the
hour-of-day and weekday clustering of the events, and a moving average.

Any event-producing metric adopts it by handing its `ReadingWindowSpec`, an `event`
name, the recurring `Window`s, and the rows — glucose (lows/highs), blood pressure
(hypertensive/hypotensive episodes), heart rate (tachy/brady), SpO2 dips, temperature
spikes … no new code path per metric.

WLJ exposes NUMBERS AND FACTS — never a verdict ("your control is getting worse"). The
conversational model reasons over the facts. Deterministic; same rows → same dict.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional, Sequence, Tuple

from apps.core.truth.history import HistorySeries, HistoryPoint
from apps.core.truth.periods import Period
from apps.core.truth.reading_window import (
    ReadingWindowSpec,
    build_reading_series,
    event_count_attr,
    event_predicate,
)
from apps.core.truth.windows import Window


# Moving-average smoothing window (in windows/days). A trailing mean over this many
# windows — long enough to damp night-to-night noise, short enough to show a shift.
_DEFAULT_MA = 7
_BY_TIME_CAP = 366          # guard the by_hour/by_weekday scan on huge event sets


@dataclass(frozen=True)
class EventFrequencyPoint:
    """One recurring window's event count. `readings` distinguishes a genuine ZERO
    ('no lows that night') from NO DATA ('the CGM wasn't recording') — the invariant
    that a missing metric is never silently counted as compliant."""
    date: date
    label: str
    count: int
    readings: int           # how many readings the window had (0 → no data, not "zero events")


@dataclass(frozen=True)
class EventFrequencySeries:
    domain: str
    metric: str
    event: str
    unit: Optional[str]
    window_kind: str
    period_label: str
    points: Tuple[EventFrequencyPoint, ...]
    total_events: int
    windows_with_data: int
    event_times: Tuple[datetime, ...]      # every event's timestamp (for by_hour/by_weekday)
    thresholds: dict
    clamped: bool = False

    def present(self):
        # Present when at least one window actually held data — 0 events over windows
        # that DID have readings is a real, meaningful answer ("no lows"); 0 windows with
        # data is an honest empty ("nothing recorded"), not "no events".
        return self.windows_with_data > 0

    # -- frequency analytics (NOT owned by Trend) -----------------------------
    # Every rate/average/trend is computed over windows that ACTUALLY HAD DATA — a night
    # with no reading is UNKNOWN, never a fabricated "0 events" (the empty-vs-zero
    # invariant). A window that had data and genuinely no event still counts as a real 0.
    def _data_points(self):
        return [p for p in self.points if p.readings > 0]

    def _counts(self):
        return [p.count for p in self._data_points()]

    def windows_count(self):
        """Windows that had data (the measured denominator), NOT every resolved window."""
        return self.windows_with_data

    def average_events_per_window(self):
        n = self.windows_with_data
        return round(self.total_events / n, 2) if n else None

    def windows_with_event(self):
        return sum(1 for c in self._counts() if c > 0)

    def event_rate(self):
        """Fraction of MEASURED windows that had at least one event — 'how often does this
        happen at all' (0.20 = a low on 1 measured night in 5), distinct from the average
        per window. Denominator is windows-with-data, never fabricated no-data zeros."""
        n = self.windows_with_data
        return round(self.windows_with_event() / n, 3) if n else None

    def _extreme_window(self, pick):
        pts = self._data_points()
        if not pts:
            return None
        p = pick(pts, key=lambda p: p.count)
        return {"date": p.date.isoformat(), "count": p.count, "label": p.label}

    def highest_window(self):
        return self._extreme_window(max)

    def lowest_window(self):
        return self._extreme_window(min)

    def moving_average(self, window=_DEFAULT_MA):
        """Trailing mean of the event counts on MEASURED windows (smooths night-to-night
        noise). One value per data window, over the last `window` measured points."""
        out, pts = [], self._data_points()
        counts = [p.count for p in pts]
        for i, p in enumerate(pts):
            seg = counts[max(0, i - window + 1): i + 1]
            out.append({"date": p.date.isoformat(),
                        "value": round(sum(seg) / len(seg), 2) if seg else None})
        return out

    def by_hour(self):
        """Hour-of-day (local 0–23) clustering of the EVENTS themselves — the
        deterministic answer to 'what time of night do my lows occur' / 'do dangerous
        events cluster after dinner'. Peak hour = the hour with the most events."""
        buckets = {}
        for t in self.event_times[:_BY_TIME_CAP * 4]:
            buckets[t.hour] = buckets.get(t.hour, 0) + 1
        if not buckets:
            return None
        peak = max(buckets, key=lambda h: buckets[h])
        return {"hours": {str(h): buckets[h] for h in sorted(buckets)},
                "peak_hour": peak}

    def by_weekday(self):
        """Weekday clustering of the events (Mon=0 … Sun=6) — 'do my lows cluster on
        certain days'. Peak weekday = the day with the most events."""
        names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        buckets = {}
        for t in self.event_times[:_BY_TIME_CAP * 4]:
            buckets[t.weekday()] = buckets.get(t.weekday(), 0) + 1
        if not buckets:
            return None
        peak = max(buckets, key=lambda w: buckets[w])
        return {"weekdays": {names[w]: buckets[w] for w in sorted(buckets)},
                "peak_weekday": names[peak]}

    # -- TREND — reused, never re-implemented ---------------------------------
    def to_history_series(self):
        """The MEASURED per-window counts AS a `HistorySeries` (date → count). This is the
        seam by which TREND and COMPARISON consume the Event Frequency series with ZERO new
        analytics — `.change()` here is literally `HistorySeries.change()`. No-data windows
        are excluded so a stretch of missing readings never reads as a run of zeros that
        fakes a downward trend."""
        pts = self._data_points()
        points = tuple(HistoryPoint(p.date, p.count) for p in pts)
        period = Period(self.window_kind, pts[0].date, pts[-1].date,
                        self.period_label) if pts else \
            Period(self.window_kind, date.min, date.min, self.period_label)
        return HistorySeries(self.domain, f"{self.metric}_{self.event}_events",
                             period, points, unit="events")

    def change(self):
        """The deterministic frequency TREND (rising/falling/flat, slope, pct_change) —
        delegated to the Trend primitive. WLJ never says 'improving'; direction is
        arithmetic and the model interprets whether more/fewer events is good."""
        if self.windows_count() < 2:
            return None
        return self.to_history_series().change()

    # -- serialization --------------------------------------------------------
    def to_dict(self):
        return {
            "domain": self.domain,
            "metric": self.metric,
            "event": self.event,
            "unit": self.unit,
            "window_kind": self.window_kind,
            "period": self.period_label,
            "present": self.present(),
            "windows": self.windows_count(),
            "windows_with_data": self.windows_with_data,
            "total_events": self.total_events,
            "average_events_per_window": self.average_events_per_window(),
            "windows_with_event": self.windows_with_event(),
            "event_rate": self.event_rate(),
            "highest_window": self.highest_window(),
            "lowest_window": self.lowest_window(),
            # Frequency TREND — reused Trend math (direction/slope/pct_change). This is
            # how "are my lows getting MORE FREQUENT" is answered deterministically.
            "change": self.change(),
            "by_hour": self.by_hour(),
            "by_weekday": self.by_weekday(),
            "moving_average": self.moving_average(),
            "thresholds": self.thresholds,
            "clamped": self.clamped,
            # The raw per-window series (count + whether the window had data) so the model
            # can narrate specifics ("3 nights had lows: the 12th, 14th, 15th").
            "series": [{"date": p.date.isoformat(), "label": p.label,
                        "count": p.count, "readings": p.readings}
                       for p in self.points],
        }


def build_event_frequency_series(spec: ReadingWindowSpec, event: str,
                                 windows: Sequence[Window], rows: Sequence[Any],
                                 *, period_label: str = "") -> Optional[EventFrequencySeries]:
    """Compose an `EventFrequencySeries` for `event` across `windows` from `rows` (any
    iterable of records the caller scoped to the outer span in ONE query). Pure: no I/O.

    Reuse-only: each window's COUNT is `build_reading_series` (the reading-window stats
    engine); each event's timestamp is `event_predicate(spec, event)` (the reading-window
    thresholds). Returns None when the spec lacks the threshold `event` requires (the
    caller then reports honestly, never a fabricated zero)."""
    count_attr = event_count_attr(event)
    predicate = event_predicate(spec, event)
    if count_attr is None or predicate is None:
        return None

    vg, tg = spec.value_getter, spec.time_getter

    # Prepare (time, value, row) once, in ascending time — reused across every window.
    prepared = []
    for r in rows:
        try:
            v = vg(r)
            t = tg(r)
        except Exception:
            continue
        if v is None or t is None:
            continue
        prepared.append((t, float(v), r))
    prepared.sort(key=lambda p: p[0])

    thresholds = {"low": spec.low, "high": spec.high,
                  "urgent_low": spec.urgent_low, "urgent_high": spec.urgent_high}

    points = []
    total_events = 0
    windows_with_data = 0
    event_times: list = []
    clamped = False

    for w in windows:
        if getattr(w, "clamped", False):
            clamped = True
        bucket_rows, bucket_pairs = [], []
        for t, v, r in prepared:
            if w.start <= t <= w.end:
                bucket_rows.append(r)
                bucket_pairs.append((t, v))
        # COUNT via the reading-window stats engine (single-sourced), not a new counter.
        series = build_reading_series(spec, w, bucket_rows)
        count = getattr(series, count_attr) or 0
        readings = series.count
        if readings > 0:
            windows_with_data += 1
        total_events += count
        # Event timestamps via the SAME thresholds — for by_hour / by_weekday clustering.
        for t, v in bucket_pairs:
            if predicate(v):
                event_times.append(t)
        anchor = w.start.date()
        points.append(EventFrequencyPoint(date=anchor, label=w.label,
                                          count=count, readings=readings))

    return EventFrequencySeries(
        domain=spec.domain, metric=spec.metric, event=(event or "").strip().lower(),
        unit=spec.unit, window_kind=(windows[0].name if windows else ""),
        period_label=period_label, points=tuple(points),
        total_events=total_events, windows_with_data=windows_with_data,
        event_times=tuple(event_times), thresholds=thresholds, clamped=clamped)
