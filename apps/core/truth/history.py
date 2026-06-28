"""
Platform capability: POINT-IN-TIME HISTORY.

The authoritative object for "what was the user's X over a period" — the symmetric
half of Current Truth (which answers "now"). A `HistorySeries` is an ordered set of
(date, value) points over a resolved `Period`, with deterministic aggregates
(total / average / max / min / count / latest / earliest).

Every domain exposes History via a small provider that runs ONE grouped query over
the range and hands the rows here (`series_from_rows`). The platform owns the period
resolution, the series object, and the aggregates; the domain owns only its query.
Beth retrieves History for "back then" questions; Current Truth for "now".
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional, Sequence, Tuple

from apps.core.truth.periods import Period


@dataclass(frozen=True)
class HistoryPoint:
    date: date
    value: Any


@dataclass(frozen=True)
class HistorySeries:
    domain: str
    metric: str
    period: Period
    points: Tuple[HistoryPoint, ...]
    unit: Optional[str] = None

    # -- presence -------------------------------------------------------------
    def present(self):
        return bool(self.points)

    # -- aggregates (deterministic; empty-safe) -------------------------------
    def values(self):
        return [p.value for p in self.points]

    def total(self):
        return sum(self.values()) if self.points else 0

    def average(self):
        return (self.total() / len(self.points)) if self.points else None

    def maximum(self):
        return max(self.values()) if self.points else None

    def minimum(self):
        return min(self.values()) if self.points else None

    def count(self):
        """Number of data points (e.g. days/sessions with a value)."""
        return len(self.points)

    def confidence(self):
        """Law 2 — confidence from coverage: how much of the period has data."""
        from apps.core.truth.confidence import confidence_from_coverage
        return confidence_from_coverage(self.count(), self.period.days())

    def latest(self):
        return self.points[-1] if self.points else None

    def earliest(self):
        return self.points[0] if self.points else None

    # -- serialization --------------------------------------------------------
    def to_dict(self):
        return {
            "domain": self.domain,
            "metric": self.metric,
            "period": self.period.label,
            "start": self.period.start.isoformat(),
            "end": self.period.end.isoformat(),
            "unit": self.unit,
            "present": self.present(),
            "count": self.count(),
            "total": self.total(),
            "average": self.average(),
            "confidence": self.confidence(),
            "points": [{"date": p.date.isoformat(), "value": p.value}
                       for p in self.points],
        }


def series_from_rows(domain, metric, period, rows, *, unit=None,
                     date_key="date", value_key="value"):
    """Build a `HistorySeries` from a domain's grouped query rows (ascending date).

    `rows` is any sequence of mappings with a date and a value under the given keys.
    Rows are sorted by date defensively so callers needn't guarantee order.
    """
    points = tuple(
        HistoryPoint(r[date_key], r[value_key])
        for r in sorted(rows, key=lambda r: r[date_key])
    )
    return HistorySeries(domain, metric, period, points, unit)
