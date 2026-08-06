"""
Platform capability support: PERIOD RESOLUTION.

Domain-agnostic date math that turns a named period ("yesterday", "last week",
"this month", "last quarter", "this year") or an explicit (start, end) into a
concrete `Period`. Owned once here so every domain's History capability resolves
ranges identically — no domain re-implements "what does last week mean".
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# Named periods this resolver understands (custom range via start/end kwargs).
NAMED_PERIODS = (
    "today", "yesterday", "last_7_days", "this_week", "last_week",
    "this_month", "last_month", "this_quarter", "last_quarter",
    "this_year", "last_year",
)

# Spoken aliases for the named periods (the model/user says "last week", the
# resolver stores "last_week"). Owned here so every surface normalizes identically.
_PERIOD_ALIASES = {
    "last 7 days": "last_7_days", "last seven days": "last_7_days",
    "past 7 days": "last_7_days", "past week": "last_7_days",
    "this week": "this_week", "last week": "last_week",
    "this month": "this_month", "last month": "last_month",
    "this quarter": "this_quarter", "last quarter": "last_quarter",
    "this year": "this_year", "last year": "last_year",
}

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6, "mon": 0, "tue": 1, "tues": 1, "wed": 2,
    "thu": 3, "thur": 4, "thurs": 4, "fri": 4, "sat": 5, "sun": 6,
}

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})  # jan, feb, ...


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


def _coerce_date(d):
    """Accept a date, datetime, or ISO 'YYYY-MM-DD' string (None passes through).
    Callers reaching this via model-supplied JSON filters send ISO strings; callers
    from Python send dates. Both must resolve identically."""
    from datetime import date as _date, datetime as _dt
    if d is None or (isinstance(d, _date) and not isinstance(d, _dt)):
        return d
    if isinstance(d, _dt):
        return d.date()
    return _dt.strptime(str(d)[:10], "%Y-%m-%d").date()


def resolve_period(name, today, *, start=None, end=None):
    """Return a `Period` for a named period (or a custom range when name=='custom').

    Args:
        name: one of NAMED_PERIODS or "custom".
        today: the user's local today (date).
        start, end: required when name == "custom" (inclusive). Accepts date or
            ISO 'YYYY-MM-DD' string (model-supplied filters arrive as strings).
    """
    start, end = _coerce_date(start), _coerce_date(end)
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


def _resolve_weekday(today, wd, modifier):
    """Concrete date for a weekday phrase relative to `today` (Mon=0..Sun=6)."""
    if modifier in ("next", "coming"):
        fwd = (wd - today.weekday()) % 7 or 7
        return today + timedelta(days=fwd)
    if modifier == "this":
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(days=wd)
    if modifier in ("last", "past"):                 # most recent BEFORE today
        back = (today.weekday() - wd) % 7 or 7
        return today - timedelta(days=back)
    back = (today.weekday() - wd) % 7                 # bare: most recent on-or-before
    return today - timedelta(days=back)


def _parse_explicit_date(phrase, today):
    """A concrete calendar date from 'July 4', 'Jul 4 2026', '7/4', '7/4/2026',
    '4 July'. Year-less phrases default to the most recent past occurrence."""
    p = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", phrase.replace(",", "")).strip()
    for fmt in ("%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y",
                "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(p, fmt).date()
        except ValueError:
            pass
    for fmt in ("%B %d", "%b %d", "%d %B", "%d %b", "%m/%d"):
        try:
            d = datetime.strptime(p, fmt).date().replace(year=today.year)
            return d.replace(year=today.year - 1) if d > today else d
        except ValueError:
            pass
    return None


_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12,
}

_OFFSET_UNITS = {"day": 1, "week": 7, "night": 1}  # a "night" is a day for date math

# Single-night relative phrases → whole-day offset back from today. A "night" names one
# calendar night, so each resolves to a single DAY (start==end). "last night" == the night
# just passed (today-1); "the night before" (i.e. the night before last night) == today-2.
# Without these, a natural date-shift follow-up ("what about the night before?") was
# unresolvable and the CoS falsely said the data was unavailable while it existed.
_RELATIVE_NIGHT_OFFSETS = {
    "last night": 1, "the last night": 1, "previous night": 1, "the previous night": 1,
    "night before": 2, "the night before": 2,
    "night before last": 2, "the night before last": 2,
    "day before yesterday": 2, "the day before yesterday": 2,
}


def _parse_relative_offset(phrase, today):
    """A concrete date for 'N days/weeks/months/years ago' ('two weeks ago',
    '3 days ago', 'a year ago'). Resolves to the single DAY that far back — the
    literal reading; it never widens into a range it cannot justify."""
    m = re.match(r"^(\d+|[a-z]+)\s+(day|week|month|year|night)s?\s+ago$", phrase)
    if not m:
        return None
    qty_raw = m.group(1)
    qty = int(qty_raw) if qty_raw.isdigit() else _NUMBER_WORDS.get(qty_raw)
    if not qty:
        return None
    unit = m.group(2)
    if unit in _OFFSET_UNITS:
        return today - timedelta(days=qty * _OFFSET_UNITS[unit])
    if unit == "month":
        total = (today.year * 12 + today.month - 1) - qty
        y, mo = divmod(total, 12)
        # clamp the day into the target month (e.g. Mar 31 → Feb 28)
        mo += 1
        for day in range(today.day, 0, -1):
            try:
                return date(y, mo, day)
            except ValueError:
                continue
        return None
    # year
    try:
        return today.replace(year=today.year - qty)
    except ValueError:                      # Feb 29 → Feb 28
        return today.replace(year=today.year - qty, day=28)


def resolve_date_expression(phrase, today):
    """Resolve a natural date PHRASE to a concrete `Period` (single day → start==end),
    or None if unparseable. The ONE shared conversational date resolver — every truth
    surface normalizes 'today' / 'yesterday' / 'last Tuesday' / 'July 4' / 'last week'
    identically, BEFORE the phrase reaches any domain provider. Deterministic; no
    external libraries. Extends `resolve_period` (named periods) with weekdays and
    explicit calendar dates; it never invents a range it cannot justify.
    """
    if phrase is None:
        return None
    p = " ".join(str(phrase).strip().lower().split())
    if not p:
        return None
    if p in NAMED_PERIODS:
        return resolve_period(p, today)
    if p in _PERIOD_ALIASES:
        return resolve_period(_PERIOD_ALIASES[p], today)
    if p in _RELATIVE_NIGHT_OFFSETS:                  # "the night before", "night before last"
        d = today - timedelta(days=_RELATIVE_NIGHT_OFFSETS[p])
        return Period(p, d, d, p)
    # Trailing "last/past N days|weeks|months" → the inclusive window ending today (e.g.
    # 'last 30 days' = today-29 … today). Owned here so every surface resolves it identically.
    m = re.match(r"^(?:last|past)\s+(\d{1,4})\s+(day|week|month)s?$", p)
    if m:
        qty = int(m.group(1))
        unit = m.group(2)
        if qty >= 1:
            days = qty * {"day": 1, "week": 7, "month": 30}[unit]
            start = today - timedelta(days=days - 1)
            return Period(p, start, today, f"the last {qty} {unit}{'s' if qty != 1 else ''}")
    try:                                              # ISO 'YYYY-MM-DD'
        d = datetime.strptime(p[:10], "%Y-%m-%d").date()
        return Period(p, d, d, p)
    except ValueError:
        pass
    m = re.match(r"^(last|this|next|past|coming)?\s*([a-z]+)$", p)
    if m and m.group(2) in _WEEKDAYS:
        d = _resolve_weekday(today, _WEEKDAYS[m.group(2)], m.group(1))
        return Period(p, d, d, p)
    d = _parse_explicit_date(p, today)
    if d:
        return Period(p, d, d, p)
    d = _parse_relative_offset(p, today)
    if d:
        return Period(p, d, d, p)
    return None
