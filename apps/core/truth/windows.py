"""
Platform capability: TIME-WINDOW RESOLUTION (intra-day / high-frequency).

The datetime companion to `periods.py`. `periods.py` answers "which DAYS" (a `Period`
of whole calendar dates); `windows.py` answers "which MOMENTS" — an arbitrary
[start, end] datetime interval for HIGH-FREQUENCY metrics (glucose CGM every 5 min,
heart rate, SpO2, temperature, respiration, sleep stages, activity …).

Owned once here so every domain resolves "overnight" / "past 12 hours" / "since
midnight" / "this morning" / "last night" identically — the same way `periods.py`
owns "last week". Deterministic; no external libraries; never invents a window it
cannot justify (unparseable → None → the caller rejects honestly).

WHY this is separate from `periods.py`: a whole-day `Period` cannot express "the last
12 hours" or "midnight to 6 AM" — its granularity is the calendar date. A glucose low
at 03:12 is invisible to a per-day surface. This module is the ONE place intra-day
truth is scoped, so no domain re-implements hour math.
"""
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta


# The longest window this resolver will hand back. High-frequency series (5-min CGM ≈
# 288 rows/day) stay bounded on the request path — a caller asking for "the last year"
# of raw readings is clamped to this and told so (a Window is intra-day by intent).
MAX_WINDOW_HOURS = 7 * 24


@dataclass(frozen=True)
class Window:
    """A resolved [start, end] moment interval (both timezone-aware), plus a human
    label and the natural-language `name` that produced it. `clamped` is True when the
    requested span exceeded MAX_WINDOW_HOURS and `start` was pulled forward."""
    name: str
    start: datetime
    end: datetime
    label: str
    clamped: bool = False

    def hours(self):
        return (self.end - self.start).total_seconds() / 3600.0

    def to_dict(self):
        return {
            "name": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
            "hours": round(self.hours(), 2),
            "clamped": self.clamped,
        }


_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "twenty-four": 24, "twenty four": 24, "half": 0,
}

# "the overnight window" — local midnight to 6 AM, the clinical fasting/nocturnal
# window (matches build_glucose_summary's overnight aggregate). Deterministic bounds.
_OVERNIGHT_START_HOUR = 0
_OVERNIGHT_END_HOUR = 6


def _at(day_dt, hour):
    """A tz-aware datetime at `hour:00` on the same local day as `day_dt`."""
    return day_dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def _clamp(name, start, end, label):
    """Enforce MAX_WINDOW_HOURS by pulling `start` forward; flag it so the caller can
    tell the model the window was shortened (never silently truncated)."""
    span_h = (end - start).total_seconds() / 3600.0
    if span_h > MAX_WINDOW_HOURS:
        return Window(name, end - timedelta(hours=MAX_WINDOW_HOURS), end, label,
                      clamped=True)
    return Window(name, start, end, label)


def _parse_hours(p):
    """Number of hours from 'past 12 hours' / 'last 6 hrs' / 'last hour' / '24h'.
    Returns a float count or None."""
    m = re.match(
        r"^(?:the\s+)?(?:past|last|previous|prior)?\s*"
        r"(\d+(?:\.\d+)?|[a-z\- ]+?)?\s*"
        r"(hours?|hrs?|h)$", p)
    if not m:
        return None
    qty_raw = (m.group(1) or "").strip()
    if qty_raw == "":
        qty = 1.0                      # "last hour" / "the hour"
    elif re.match(r"^\d+(?:\.\d+)?$", qty_raw):
        qty = float(qty_raw)
    else:
        qty = _NUMBER_WORDS.get(qty_raw)
        if qty is None:
            return None
        qty = float(qty)
    return qty if qty > 0 else None


def resolve_window(phrase, now):
    """Resolve a natural intra-day PHRASE to a concrete `Window`, or None if unparseable.

    `now` MUST be the user's timezone-aware LOCAL now (callers pass `get_user_now(user)`)
    — every relative window ("past 12 hours", "since midnight") is measured against it,
    never UTC. Deterministic; the ONE shared intra-day resolver.

    Understood phrases (case/spacing-insensitive):
        overnight | last night | tonight     → local 00:00 → 06:00 (nocturnal window)
        this morning                         → local 00:00 → 12:00 (clamped to now)
        this afternoon                       → local 12:00 → 18:00 (clamped to now)
        this evening                         → local 18:00 → now
        today | since midnight | so far today→ local 00:00 → now
        yesterday                            → local prev-day 00:00 → 24:00
        past/last N hours | last hour | 24h  → now − N hours → now

    A DAY phrase this resolver does not special-case ("last Tuesday", "July 4") is NOT
    its job — that is `periods.py`. Returns None so the caller can fall back to a day
    period. Never raises.
    """
    if phrase is None:
        return None
    p = " ".join(str(phrase).strip().lower().split())
    if not p:
        return None
    p = p.rstrip("?.!")
    p = p.strip()

    today0 = _at(now, 0)                      # local midnight today (aware)

    # -- overnight / last night -> nocturnal window (00:00–06:00 local) ----------
    if p in ("overnight", "last night", "tonight", "over night", "during the night",
             "in the night", "through the night"):
        start = _at(today0, _OVERNIGHT_START_HOUR)
        end = _at(today0, _OVERNIGHT_END_HOUR)
        if now < end:                        # asked DURING the night → up to now
            end = now
        return Window("overnight", start, end, "overnight (12:00 AM–6:00 AM)")

    # -- since midnight / today so far ------------------------------------------
    if p in ("today", "since midnight", "so far today", "today so far",
             "midnight to now", "since this morning", "so far"):
        return Window("today", today0, now, "since midnight")

    # -- parts of the day -------------------------------------------------------
    if p in ("this morning", "the morning"):
        end = min(now, _at(today0, 12))
        return Window("this_morning", today0, end, "this morning")
    if p in ("this afternoon", "the afternoon"):
        start = _at(today0, 12)
        end = min(now, _at(today0, 18))
        if now < start:
            return None
        return Window("this_afternoon", start, end, "this afternoon")
    if p in ("this evening", "the evening", "tonight so far"):
        start = _at(today0, 18)
        if now < start:
            return None
        return Window("this_evening", start, now, "this evening")

    # -- yesterday (full local day) ---------------------------------------------
    if p == "yesterday":
        start = today0 - timedelta(days=1)
        return Window("yesterday", start, today0, "yesterday")

    # -- past / last N hours -----------------------------------------------------
    hrs = _parse_hours(p)
    if hrs is not None:
        start = now - timedelta(hours=hrs)
        label = ("the last hour" if abs(hrs - 1.0) < 1e-9
                 else f"the last {hrs:g} hours")
        return _clamp("last_hours", start, now, label)

    return None


def window_from_period(period, now):
    """Widen a whole-day `Period` (from `periods.py`) into a `Window` spanning local
    midnight of `period.start` to end-of-day of `period.end` — clamped to `now` when
    the period includes today. Lets a day phrase ("last Tuesday", "July 4") that a
    caller already resolved as a `Period` flow through the intra-day reading surface
    without re-parsing. `now` is the user's aware local now."""
    start = now.replace(year=period.start.year, month=period.start.month,
                        day=period.start.day, hour=0, minute=0, second=0,
                        microsecond=0)
    end = now.replace(year=period.end.year, month=period.end.month,
                      day=period.end.day, hour=0, minute=0, second=0,
                      microsecond=0) + timedelta(days=1)
    end = min(end, now) if period.end >= now.date() else end
    label = getattr(period, "label", None) or period.name
    return _clamp(period.name, start, end, label)
