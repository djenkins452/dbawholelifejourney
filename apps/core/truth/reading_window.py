"""
Platform capability: READING-WINDOW SERIES (intra-day / high-frequency truth).

The third shape of Layer-1 numeric truth, alongside:
    * CURRENT   — the single "now" scalar (CurrentTruth)
    * HISTORY   — a per-DAY aggregate trend over a Period (HistorySeries)
    * READINGS  — the individual timestamped SAMPLES inside a datetime Window,
                  plus deterministic window statistics and excursions  ← THIS

HISTORY collapses a day of readings into one mean — correct for "my glucose trend
this week", useless for "what were my lows overnight". A `ReadingSeries` keeps the
individual samples and computes the window facts a person actually asks about:
count, min, max, average, time-in-range, low/high excursion counts, and the list of
excursions with their timestamps.

Domain-agnostic BY CONSTRUCTION: the producer takes rows + two accessors
(`value_getter` → canonical numeric value, `time_getter` → aware datetime) + numeric
thresholds. Glucose is the first adopter; heart rate, blood pressure, SpO2,
temperature, respiration, and future wearable metrics adopt by passing their own
accessors and thresholds — no new code path per metric.

WLJ exposes NUMBERS AND FACTS here — never a verdict ("your control is poor"). The
conversational model reasons over the facts. Deterministic; same rows → same dict.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from apps.core.truth.windows import Window


# Payload guards — a window is intra-day, but a 7-day CGM span is ~2000 samples. We
# compute STATISTICS over every row (cheap) but only SERIALIZE a bounded sample so the
# model's context is never flooded. Truncation is always flagged, never silent.
_SAMPLE_CAP = 240
_EXCURSION_CAP = 25


@dataclass(frozen=True)
class ReadingWindowSpec:
    """Per-metric configuration a domain registers once so any consumer can build the
    same reading window. `low`/`high` are the in-range band (inclusive); `urgent_low`/
    `urgent_high` are optional severe-excursion thresholds. `value_getter` MUST return
    the value already normalized to `unit` (e.g. GlucoseEntry.value_in_mg_dl)."""
    domain: str
    metric: str
    unit: str
    value_getter: Callable[[Any], Optional[float]]
    time_getter: Callable[[Any], Any]
    low: Optional[float] = None
    high: Optional[float] = None
    urgent_low: Optional[float] = None
    urgent_high: Optional[float] = None


@dataclass(frozen=True)
class Reading:
    at: str            # ISO timestamp (aware)
    value: float


@dataclass(frozen=True)
class ReadingSeries:
    domain: str
    metric: str
    window: Window
    unit: str
    count: int
    minimum: Optional[float]
    maximum: Optional[float]
    average: Optional[float]
    first: Optional[Reading]
    last: Optional[Reading]
    in_range: Optional[int]
    below_low: Optional[int]
    above_high: Optional[int]
    urgent_low_count: Optional[int]
    urgent_high_count: Optional[int]
    low_excursions: Sequence[Reading]
    samples: Sequence[Reading]
    samples_truncated: bool
    thresholds: dict
    by_hour: Optional[dict] = None      # hour-of-day distribution (see build_reading_series)

    def present(self):
        return self.count > 0

    def _pct(self, n):
        return round((n / self.count) * 100, 1) if self.count and n is not None else None

    def to_dict(self):
        return {
            "domain": self.domain,
            "metric": self.metric,
            "unit": self.unit,
            "window": self.window.to_dict(),
            "present": self.present(),
            "count": self.count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "average": self.average,
            "first": {"at": self.first.at, "value": self.first.value} if self.first else None,
            "last": {"at": self.last.at, "value": self.last.value} if self.last else None,
            "in_range": self.in_range,
            "in_range_pct": self._pct(self.in_range),
            "below_low": self.below_low,
            "below_low_pct": self._pct(self.below_low),
            "above_high": self.above_high,
            "above_high_pct": self._pct(self.above_high),
            "urgent_low_count": self.urgent_low_count,
            "urgent_high_count": self.urgent_high_count,
            "thresholds": self.thresholds,
            # Individual excursions with their timestamps — the deterministic answer to
            # "what were my lows overnight" / "when did I go low".
            "low_excursions": [{"at": r.at, "value": r.value} for r in self.low_excursions],
            # A bounded serialization of the raw samples (newest last). `samples_truncated`
            # signals more rows exist than are shown — the stats above still cover ALL rows.
            "samples": [{"at": r.at, "value": r.value} for r in self.samples],
            "samples_truncated": self.samples_truncated,
            # Hour-of-day distribution — the deterministic answer to "what TIME of day is X
            # highest/lowest" / "what time of night do my lows occur". None unless requested.
            "by_hour": self.by_hour,
        }


def _by_hour(pairs):
    """Hour-of-day (local 0–23) distribution over (aware datetime, value) pairs:
    {hour: {count, avg, min, max}} + the peak/lowest hour by average. Deterministic
    answer to 'what time of day is X highest/lowest'. Hour is read from each
    timestamp's own offset (the caller passes local-aware datetimes)."""
    buckets = {}
    for t, v in pairs:
        h = t.hour
        buckets.setdefault(h, []).append(v)
    dist = {}
    for h, vals in buckets.items():
        dist[h] = {"count": len(vals), "avg": round(sum(vals) / len(vals), 1),
                   "min": round(min(vals), 1), "max": round(max(vals), 1)}
    if not dist:
        return None
    peak = max(dist, key=lambda h: dist[h]["avg"])
    trough = min(dist, key=lambda h: dist[h]["avg"])
    return {"hours": dist, "peak_hour": peak, "lowest_hour": trough}


# ── Event selectors (Event Frequency capability reuses THESE thresholds) ──────
# The named EVENTS a reading window can count, each mapped to (a) the count attribute on
# a ReadingSeries and (b) a value predicate — both derived from the SAME spec thresholds
# build_reading_series uses. So the Event Frequency capability counts events without
# re-deriving any threshold: one source of "what is a low / a high / in range".
EVENTS = ("low", "urgent_low", "high", "urgent_high", "in_range")

_EVENT_COUNT_ATTR = {
    "low": "below_low",
    "urgent_low": "urgent_low_count",
    "high": "above_high",
    "urgent_high": "urgent_high_count",
    "in_range": "in_range",
}


def event_count_attr(event):
    """The `ReadingSeries` attribute holding the count for `event`, or None."""
    return _EVENT_COUNT_ATTR.get((event or "").strip().lower())


def event_predicate(spec: ReadingWindowSpec, event):
    """A value→bool predicate for `event`, using the SAME thresholds as
    build_reading_series. Returns None when the spec lacks the threshold that event
    needs (e.g. 'urgent_low' with no urgent_low set) — so the caller reports honestly
    rather than fabricating a zero. Deterministic; the ONE definition of each event."""
    e = (event or "").strip().lower()
    if e == "low" and spec.low is not None:
        return lambda v: v < spec.low
    if e == "urgent_low" and spec.urgent_low is not None:
        return lambda v: v < spec.urgent_low
    if e == "high" and spec.high is not None:
        return lambda v: v > spec.high
    if e == "urgent_high" and spec.urgent_high is not None:
        return lambda v: v > spec.urgent_high
    if e == "in_range" and spec.low is not None and spec.high is not None:
        return lambda v: spec.low <= v <= spec.high
    return None


def build_reading_series(spec: ReadingWindowSpec, window: Window, rows: Sequence[Any],
                         *, sample_cap: int = _SAMPLE_CAP,
                         excursion_cap: int = _EXCURSION_CAP,
                         with_by_hour: bool = False) -> ReadingSeries:
    """Compose a `ReadingSeries` from `rows` (any iterable of records) already scoped to
    `window` by the caller's query. Pure: no I/O, no DB access — the domain owns the
    query; the platform owns the statistics. Rows are read in ASCENDING time.

    Statistics are computed over EVERY row (bounded because a Window is intra-day and
    clamped by MAX_WINDOW_HOURS). Only the serialized `samples` list is capped.
    `with_by_hour` adds the hour-of-day distribution (time-of-day questions)."""
    vg, tg = spec.value_getter, spec.time_getter
    pairs = []
    for r in rows:
        try:
            v = vg(r)
            t = tg(r)
        except Exception:
            continue
        if v is None or t is None:
            continue
        pairs.append((t, float(v)))
    pairs.sort(key=lambda p: p[0])

    thresholds = {"low": spec.low, "high": spec.high,
                  "urgent_low": spec.urgent_low, "urgent_high": spec.urgent_high}

    if not pairs:
        return ReadingSeries(
            spec.domain, spec.metric, window, spec.unit, 0,
            None, None, None, None, None,
            None, None, None, None, None, [], [], False, thresholds, None)

    values = [v for _, v in pairs]
    count = len(values)
    total = sum(values)
    minimum = round(min(values), 1)
    maximum = round(max(values), 1)
    average = round(total / count, 1)

    def _n(pred):
        return sum(1 for v in values if pred(v))

    in_range = below_low = above_high = None
    if spec.low is not None and spec.high is not None:
        in_range = _n(lambda v: spec.low <= v <= spec.high)
    if spec.low is not None:
        below_low = _n(lambda v: v < spec.low)
    if spec.high is not None:
        above_high = _n(lambda v: v > spec.high)
    urgent_low_count = _n(lambda v: v < spec.urgent_low) if spec.urgent_low is not None else None
    urgent_high_count = _n(lambda v: v > spec.urgent_high) if spec.urgent_high is not None else None

    def _rd(t, v):
        return Reading(at=t.isoformat(), value=round(v, 1))

    first = _rd(*pairs[0])
    last = _rd(*pairs[-1])

    # Low excursions: the lowest readings in the window, each with its timestamp —
    # ordered by SEVERITY (lowest first) then capped, so the worst lows are never
    # dropped by truncation. Empty when no low threshold or no lows.
    low_excursions: List[Reading] = []
    if spec.low is not None:
        lows = sorted((p for p in pairs if p[1] < spec.low), key=lambda p: p[1])
        low_excursions = [_rd(t, v) for t, v in lows[:excursion_cap]]

    # Samples: bounded serialization, keeping the MOST RECENT `sample_cap` (newest last).
    truncated = count > sample_cap
    tail = pairs[-sample_cap:] if truncated else pairs
    samples = [_rd(t, v) for t, v in tail]

    return ReadingSeries(
        spec.domain, spec.metric, window, spec.unit, count,
        minimum, maximum, average, first, last,
        in_range, below_low, above_high, urgent_low_count, urgent_high_count,
        low_excursions, samples, truncated, thresholds,
        _by_hour(pairs) if with_by_hour else None)
