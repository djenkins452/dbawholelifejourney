"""
Platform capability: CONSISTENCY / REGULARITY (how much do repeated observations vary
around their normal pattern, and is that variation changing).

The fifth shape of Layer-1 numeric truth, alongside:
    * CURRENT   — the single "now" scalar (CurrentTruth)
    * HISTORY   — a per-DAY aggregate trend over a Period (HistorySeries)
    * READINGS  — the individual samples inside ONE datetime Window (ReadingSeries)
    * FREQUENCY — the COUNT of a named event across recurring windows (EventFrequencySeries)
    * CONSISTENCY — the SPREAD of a repeated observation around its center ← THIS

HISTORY answers "is my bedtime getting earlier" (the trend of the value). It cannot answer
"is my bedtime becoming more REGULAR" — that is the spread of the values, not their level.
`ConsistencyMetric` is that missing shape: for a set of dated observations of one variable,
the deterministic centre, dispersion (std dev / mean-absolute-deviation / range), the most
and least regular observations, and — split first-half vs second-half — the arithmetic
change in that dispersion ("becoming more or less regular").

CIRCULAR TIME (the midnight trap). A bedtime of 11:50 PM and one of 12:10 AM are 20 minutes
apart, not ~24 hours. Ordinary numeric variance on raw clock-minutes is WRONG for
time-of-day. A metric declared ``kind="clock"`` is treated as CIRCULAR (minute-of-day on a
1440-minute ring): centre = circular mean, dispersion = circular standard deviation, and
every deviation is the shorter arc between two times. ``kind="linear"`` (a duration, a
weight) uses ordinary statistics. No consumer re-derives either.

WLJ exposes NUMBERS AND FACTS — the centre, the spread in minutes, the arithmetic direction
of the change — never a verdict ("your schedule is inconsistent", "this hurts recovery").
The conversational model interprets whether more/less spread is good. Deterministic: the
same observations always produce the same dict. Missing observations are simply absent —
never invented as a midnight/noon reading, never counted as zero variance.

DOMAIN-AGNOSTIC BY CONSTRUCTION: any repeated numeric observation adopts it — bedtime /
wake-time regularity (clock), sleep-duration regularity (linear), meal timing, medication
timing, exercise timing, weigh-in timing … by handing dated observations + a kind. No
per-metric code path; Sleep is the first consumer.
"""
import math
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence, Tuple

_MINUTES_PER_DAY = 1440
_RAD_PER_MIN = 2.0 * math.pi / _MINUTES_PER_DAY
# Flat band for the variability-change direction: a spread change smaller than this many
# minutes (or this fraction of the larger spread) reads as "flat", not a real shift.
_FLAT_ABS_MIN = 3.0
_FLAT_REL = 0.10


def circular_diff_minutes(a: float, b: float) -> float:
    """Shortest distance in minutes between two minute-of-day values on the 24h ring
    (0..720). 11:50 PM (1430) vs 12:10 AM (10) → 20, never 1420."""
    d = abs((a - b) % _MINUTES_PER_DAY)
    return min(d, _MINUTES_PER_DAY - d)


def circular_stats(minutes: Sequence[float]) -> Optional[dict]:
    """Circular mean + standard deviation for minute-of-day values (the midnight-safe
    statistics). Returns mean_minutes (0..1440), std_minutes, and the resultant length R
    (1.0 = identical times, →0 = spread across the clock). None for an empty input."""
    n = len(minutes)
    if n == 0:
        return None
    c = sum(math.cos(m * _RAD_PER_MIN) for m in minutes)
    s = sum(math.sin(m * _RAD_PER_MIN) for m in minutes)
    r = math.sqrt(c * c + s * s) / n
    mean_min = (math.atan2(s, c) % (2.0 * math.pi)) / _RAD_PER_MIN
    # Circular standard deviation: sqrt(-2 ln R), in radians → minutes. R→1 ⇒ 0 spread.
    r_clamped = min(max(r, 1e-9), 1.0)
    std_min = math.sqrt(-2.0 * math.log(r_clamped)) / _RAD_PER_MIN
    return {"mean_minutes": mean_min, "std_minutes": std_min, "resultant": r}


def _linear_stats(values: Sequence[float]) -> Optional[dict]:
    n = len(values)
    if n == 0:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n      # population variance
    return {"mean": mean, "std": math.sqrt(var)}


def _minutes_to_clock(m: float) -> str:
    """Minute-of-day → local 'h:mm AM/PM' (presentation of a circular centre)."""
    m = int(round(m)) % _MINUTES_PER_DAY
    h24, mm = divmod(m, 60)
    ampm = "AM" if h24 < 12 else "PM"
    h12 = h24 % 12 or 12
    return f"{h12}:{mm:02d} {ampm}"


@dataclass(frozen=True)
class ConsistencyMetric:
    """The regularity of ONE repeated observation over a period.

    `kind` is "clock" (minute-of-day, circular — bedtime/wake) or "linear" (duration,
    weight …). `points` are (date, value) in ascending date; value is minute-of-day for a
    clock metric, the native unit for a linear one. Pure: no I/O; same points → same dict.
    """
    subject: str
    field: str
    kind: str                       # "clock" | "linear"
    unit: str                       # "minutes" for clock; native unit for linear
    points: Tuple[Tuple[date, float], ...]

    def _values(self):
        return [v for _, v in self.points]

    def n(self):
        return len(self.points)

    def _stats(self, values):
        if self.kind == "clock":
            cs = circular_stats(values)
            if cs is None:
                return None
            return {"center": cs["mean_minutes"], "std": cs["std_minutes"],
                    "resultant": cs["resultant"]}
        ls = _linear_stats(values)
        if ls is None:
            return None
        return {"center": ls["mean"], "std": ls["std"]}

    def _deviation(self, value, center):
        if self.kind == "clock":
            return circular_diff_minutes(value, center)
        return abs(value - center)

    def variability_change(self):
        """Arithmetic change in DISPERSION across the period: std of the first half of the
        observations vs the second half. Returns first/last std + delta + direction
        (rising = spreading OUT / less regular, falling = tightening / more regular, flat =
        no meaningful change). FACTS ONLY — WLJ never says which is 'better'. None with < 4
        observations (too few to split)."""
        pts = self.points
        if len(pts) < 4:
            return None
        mid = len(pts) // 2
        a = self._stats([v for _, v in pts[:mid]])
        b = self._stats([v for _, v in pts[mid:]])
        if not a or not b:
            return None
        first_std, last_std = round(a["std"], 1), round(b["std"], 1)
        delta = round(last_std - first_std, 1)
        band = max(_FLAT_ABS_MIN, _FLAT_REL * max(first_std, last_std))
        if abs(delta) < band:
            direction = "flat"
        else:
            direction = "rising" if delta > 0 else "falling"
        return {"first_half_std": first_std, "last_half_std": last_std,
                "delta": delta, "direction": direction,
                "first_half_n": mid, "last_half_n": len(pts) - mid}

    def to_dict(self):
        n = self.n()
        base = {"field": self.field, "kind": self.kind, "unit": self.unit,
                "observations": n}
        # Fewer than two observations has NO spread to report — return honestly
        # (present=False, no fabricated std_dev/deviation of 0.0).
        if n < 2:
            base["present"] = False
            return base
        values = self._values()
        st = self._stats(values)
        devs = [self._deviation(v, st["center"]) for v in values]
        mad = sum(devs) / len(devs)
        # Most / least regular observation = smallest / largest deviation from centre.
        idx_min = min(range(n), key=lambda i: devs[i])
        idx_max = max(range(n), key=lambda i: devs[i])
        obs = [{"date": d.isoformat(),
                "value_minutes" if self.kind == "clock" else "value":
                    (int(round(v)) if self.kind == "clock" else round(v, 2)),
                "deviation_minutes" if self.kind == "clock" else "deviation":
                    round(devs[i], 1)}
               for i, (d, v) in enumerate(self.points)]
        if self.kind == "clock":
            obs = [dict(o, clock=_minutes_to_clock(self.points[i][1]))
                   for i, o in enumerate(obs)]
        base.update({
            "present": n >= 2,             # a single observation has no spread to report
            "std_dev": round(st["std"], 1),
            "mean_abs_deviation": round(mad, 1),
            "min_deviation": round(min(devs), 1),   # closest observation to the centre
            "max_deviation": round(max(devs), 1),   # farthest — the widest single swing
            "most_regular": {"date": self.points[idx_min][0].isoformat(),
                             "deviation": round(devs[idx_min], 1)},
            "least_regular": {"date": self.points[idx_max][0].isoformat(),
                              "deviation": round(devs[idx_max], 1)},
            "variability_change": self.variability_change(),
            "observations_series": obs,
        })
        if self.kind == "clock":
            base["typical_time"] = _minutes_to_clock(st["center"])
            base["typical_minutes"] = int(round(st["center"]))
            base["resultant"] = round(st["resultant"], 3)
        else:
            base["mean"] = round(st["center"], 2)
        return base
