"""
Platform capability: CHANGE-POINT DETECTION (did the trend materially shift, and when).

The sixth analytic over Layer-1 history, composing the existing shapes:
    * HISTORY   — the (date, value) series over a Period (HistorySeries)
    * TREND     — the ONE direction/slope over that whole series (HistorySeries.change)
    * CHANGE POINT — the single date WITHIN the series where describing it as TWO trend
      segments is materially better than ONE continuous trend ← THIS

TREND answers "which way is my weight moving over the period". CHANGE POINT answers a
different question: "did the behaviour SHIFT within the period, and where" — "when did my
weight trend start improving", "when did the recent decline begin". It never replaces
Trend; it composes the SAME (date, value) history and reports pre/post trends using the
SAME rising/falling/flat definition.

METHOD (deterministic, auditable, dependency-light): segmented linear regression by
residual reduction. Fit one least-squares line to the whole series; then, for every
candidate split that satisfies the evidence guards, fit two lines and measure how much of
the single-line squared error the split removes. The best split is accepted ONLY when it
removes at least `min_residual_reduction` of the error. x is the ACTUAL day-offset from the
first observation (irregular sampling is respected), not the observation index.

FACTS, NOT A VERDICT (I.3/I.4): WLJ reports the change date, the pre/post slopes and
arithmetic directions, the slope delta, and the residual reduction — a CONCRETE, named
statistic (the fraction of squared error the segmentation removes), never a vague
"confidence: high". The model decides whether the shift is "an acceleration", "encouraging",
or "when your habit change kicked in", and never gets a fabricated date: when no split meets
the bar, the honest answer is "no supported change point" (absence of evidence is truth).

REUSE-ONLY & DOMAIN-AGNOSTIC: consumes any canonical `HistorySeries` (weight, glucose,
resting HR, sleep duration, steps, a financial metric …) — weight is the first consumer.
No per-domain regression, no second History/Trend, no ML dependency.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence, Tuple

# The rising/falling/flat band, taken from the Trend authority so direction is defined ONCE.
from apps.core.truth.history import HistorySeries as _HS

_FLAT_REL_BAND = _HS._FLAT_REL_BAND

# Evidence guards — conservative defaults for ordinary personal-health data, deliberately
# NOT tuned to any user's series. A caller may override per metric.
DEFAULT_MIN_OBS = 8               # too few points can't distinguish a shift from noise
DEFAULT_MIN_SEGMENT_POINTS = 3    # each side needs enough points to define a trend
DEFAULT_MIN_SEGMENT_DAYS = 5      # …and enough real time (irregular sampling safe)
DEFAULT_MIN_RESIDUAL_REDUCTION = 0.50   # two lines must remove >=50% of the one-line error


def _direction(first_val, last_val):
    """Arithmetic rising/falling/flat, using the SAME rule as HistorySeries.change() — never
    a new definition. Flat when the change is within 0.5% of the magnitude."""
    delta = last_val - first_val
    mag = max(abs(first_val), abs(last_val)) or 1.0
    if abs(delta) < _FLAT_REL_BAND * mag:
        return "flat"
    return "rising" if delta > 0 else "falling"


def _fit(xs, ys):
    """Least-squares line over (x, y). Returns (slope, intercept, sse) where sse is the sum
    of squared residuals. Deterministic; empty-safe for the caller's guarded ranges."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:                       # all-same-x (can't happen with distinct dates)
        slope, intercept = 0.0, my
    else:
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        intercept = my - slope * mx
    sse = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    return slope, intercept, sse


def _segment_facts(dates, xs, ys):
    """Pre/post segment description — slope PER DAY (concrete, day-offset regression) plus the
    arithmetic direction (shared Trend rule) and span."""
    slope, _, _ = _fit(xs, ys)
    return {
        "slope_per_day": round(slope, 4),
        "direction": _direction(ys[0], ys[-1]),
        "first_value": round(ys[0], 2),
        "last_value": round(ys[-1], 2),
        "first_date": dates[0].isoformat(),
        "last_date": dates[-1].isoformat(),
        "span_days": (dates[-1] - dates[0]).days,
        "observations": len(ys),
    }


@dataclass(frozen=True)
class ChangePointResult:
    domain: str
    metric: str
    period_label: str
    dates: Tuple[date, ...]
    values: Tuple[float, ...]
    # thresholds actually applied (audit)
    min_obs: int
    min_seg_points: int
    min_seg_days: int
    min_reduction: float

    def to_dict(self):
        n = len(self.values)
        base = {"domain": self.domain, "metric": self.metric,
                "period": self.period_label, "observations": n,
                "thresholds": {"min_observations": self.min_obs,
                               "min_segment_points": self.min_seg_points,
                               "min_segment_days": self.min_seg_days,
                               "min_residual_reduction": self.min_reduction}}
        if n < self.min_obs:
            base.update({"present": n > 0, "supported": False,
                         "reason": (f"Only {n} observations; need at least {self.min_obs} "
                                    f"to distinguish a real trend change from noise.")})
            return base

        dates = list(self.dates)
        xs = [(d - dates[0]).days for d in dates]
        ys = list(self.values)
        _, _, sse_single = _fit(xs, ys)
        overall_slope, _, _ = _fit(xs, ys)
        overall = {"slope_per_day": round(overall_slope, 4),
                   "direction": _direction(ys[0], ys[-1])}

        # A perfectly linear series has nothing to split.
        if sse_single <= 1e-9:
            base.update({"present": True, "supported": False, "overall": overall,
                         "reason": "The series is already a single straight trend "
                                   "(no residual to reduce)."})
            return base

        best = None                       # (sse_two, k) — min sse_two, tie → smallest k
        for k in range(self.min_seg_points, n - self.min_seg_points + 1):
            da, db = dates[:k], dates[k:]
            if (da[-1] - da[0]).days < self.min_seg_days:
                continue
            if (db[-1] - db[0]).days < self.min_seg_days:
                continue
            _, _, sse_a = _fit(xs[:k], ys[:k])
            _, _, sse_b = _fit(xs[k:], ys[k:])
            sse_two = sse_a + sse_b
            if best is None or sse_two < best[0] - 1e-12:
                best = (sse_two, k)

        if best is None:
            base.update({"present": True, "supported": False, "overall": overall,
                         "reason": (f"No candidate split leaves at least "
                                    f"{self.min_seg_points} observations and "
                                    f"{self.min_seg_days} days on both sides.")})
            return base

        sse_two, k = best
        reduction = (sse_single - sse_two) / sse_single if sse_single > 0 else 0.0
        reduction = round(max(0.0, reduction), 3)
        if reduction < self.min_reduction:
            base.update({"present": True, "supported": False, "overall": overall,
                         "best_residual_reduction": reduction,
                         "reason": (f"The best split only removes {int(reduction * 100)}% "
                                    f"of the single-trend error (needs "
                                    f"{int(self.min_reduction * 100)}%); the period is best "
                                    f"described as one continuous trend.")})
            return base

        pre = _segment_facts(dates[:k], xs[:k], ys[:k])
        post = _segment_facts(dates[k:], xs[k:], ys[k:])
        base.update({
            "present": True, "supported": True,
            "change_date": dates[k].isoformat(),
            "observations_before": k, "observations_after": n - k,
            "pre_change": pre, "post_change": post,
            "slope_delta_per_day": round(post["slope_per_day"] - pre["slope_per_day"], 4),
            "residual_reduction": reduction,      # the concrete, named strength statistic
            "sse_single": round(sse_single, 3),
            "sse_segmented": round(sse_two, 3),
            "overall": overall,
        })
        return base


def detect_change_point(points, *, domain="", metric="", period_label="",
                        min_observations=DEFAULT_MIN_OBS,
                        min_segment_points=DEFAULT_MIN_SEGMENT_POINTS,
                        min_segment_days=DEFAULT_MIN_SEGMENT_DAYS,
                        min_residual_reduction=DEFAULT_MIN_RESIDUAL_REDUCTION):
    """Detect a single supported trend change in `points` — a sequence of (date, value),
    one value per DATE (the caller passes canonical per-day history, so dates are distinct
    and already deduplicated). Returns the result dict (see ChangePointResult.to_dict).
    Pure: no I/O; same points → same dict."""
    clean = sorted(((d, float(v)) for d, v in points if v is not None),
                   key=lambda p: p[0])
    dates = tuple(d for d, _ in clean)
    values = tuple(v for _, v in clean)
    return ChangePointResult(
        domain=domain, metric=metric, period_label=period_label,
        dates=dates, values=values,
        min_obs=min_observations, min_seg_points=min_segment_points,
        min_seg_days=min_segment_days, min_reduction=min_residual_reduction,
    ).to_dict()


def change_point_from_history(series, *, period_label="", **thresholds):
    """Detect a change point in a platform `HistorySeries` — the reuse seam. Consumes the
    series' own (date, value) points (never a re-query, never a second History). Returns the
    result dict, or an insufficient/empty result honestly."""
    pts = [(p.date, p.value) for p in getattr(series, "points", ())]
    return detect_change_point(
        pts, domain=getattr(series, "domain", ""), metric=getattr(series, "metric", ""),
        period_label=period_label or getattr(getattr(series, "period", None), "label", ""),
        **thresholds)
