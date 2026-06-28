"""
Platform capability support: PERIOD RESOLUTION.

Domain-agnostic date math that turns a named period ("yesterday", "last week",
"this month", "last quarter", "this year") or an explicit (start, end) into a
concrete `Period`. Owned once here so every domain's History capability resolves
ranges identically — no domain re-implements "what does last week mean".
"""
from dataclasses import dataclass
from datetime import date, timedelta

# Named periods this resolver understands (custom range via start/end kwargs).
NAMED_PERIODS = (
    "today", "yesterday", "last_7_days", "this_week", "last_week",
    "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year",
)


@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date          # inclusive
    label: str

    def days(self):
        return (self.end - self.start).days + 1


def _quarter_start(d):
    return date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)


def resolve_period(name, today, *, start=None, end=None):
    """Return a `Period` for a named period (or a custom range when name=='custom').

    Args:
        name: one of NAMED_PERIODS or "custom".
        today: the user's local today (date).
        start, end: required when name == "custom" (inclusive).
    """
    if name == "custom":
        if not (start and end):
            raise ValueError("custom period requires start and end")
        return Period("custom", start, end, f"{start.isoformat()}–{end.isoformat()}")

    if name == "today":
        return Period(name, today, today, "today")
    if name == "yesterday":
        y = today - timedelta(days=1)
        return Period(name, y, y, "yesterday")
    if name == "last_7_days":
        return Period(name, today - timedelta(days=6), today, "the last 7 days")
    if name == "this_week":
        s = today - timedelta(days=today.weekday())          # Monday
        return Period(name, s, today, "this week")
    if name == "last_week":
        this_mon = today - timedelta(days=today.weekday())
        return Period(name, this_mon - timedelta(days=7),
                      this_mon - timedelta(days=1), "last week")
    if name == "this_month":
        return Period(name, today.replace(day=1), today, "this month")
    if name == "last_month":
        last_end = today.replace(day=1) - timedelta(days=1)
        return Period(name, last_end.replace(day=1), last_end, "last month")
    if name == "this_quarter":
        return Period(name, _quarter_start(today), today, "this quarter")
    if name == "last_quarter":
        last_end = _quarter_start(today) - timedelta(days=1)
        return Period(name, _quarter_start(last_end), last_end, "last quarter")
    if name == "this_year":
        return Period(name, date(today.year, 1, 1), today, "this year")
    if name == "last_year":
        y = today.year - 1
        return Period(name, date(y, 1, 1), date(y, 12, 31), "last year")

    raise ValueError(f"unknown period: {name!r}")
