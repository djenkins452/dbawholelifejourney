"""
Platform capability: TIMESTAMP PRECISION.

WLJ is a truth platform, so a timestamp must never claim more precision than its source
actually provided. A HealthKit heart-rate sample is precise to the SECOND; a daily step
aggregate is precise only to the DAY; a future integration may give only a MONTH or a
YEAR. Storing a date-only value at "noon" (or midnight) FABRICATES sub-day precision —
and, before local noon, fabricates a value in the FUTURE. That is exactly the class of
bug behind the Health Sync "Newest data · Today · 12:00 PM at 6 AM" incident, and it must
be made structurally impossible rather than patched case by case.

This module owns ONE vocabulary and the deterministic rules for it, so every domain
resolves and renders timestamp precision identically instead of re-inventing noon:

  * ``Precision``               — the ordered vocabulary (SECOND < MINUTE < HOUR < DAY
                                  < MONTH < YEAR), plus UNKNOWN (coarser than all).
  * ``infer_precision(raw)``    — the precision a raw source value actually carries.
  * ``resolve_instant(value, …)`` — the ONE way to turn a source value into
                                  ``(aware_datetime | None, precision)`` for storage. It
                                  NEVER fabricates a future instant, and it reports the
                                  true precision so nothing below it is ever trusted.
  * ``format_instant(dt, precision, now)`` — render a stored instant HONESTLY at its
                                  precision ("Today", "July 20", "5:54 AM", "July 2026",
                                  "2026") — never a fabricated clock time for a DAY value.

Companion to ``temporal.py`` (future-timestamp sanity). PERSISTING a precision value
alongside each observed timestamp is a phased, per-domain rollout — see
``docs/WLJ_TIMESTAMP_PRECISION.md``. Until a domain stores precision, this module still
guarantees the storage instant is never fabricated into the future, and gives every
presentation layer a single honest formatter to adopt.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

from django.utils import timezone


class Precision:
    """The canonical, ordered precision vocabulary. String values (JSON/DB friendly)."""

    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"

    # Finest → coarsest. UNKNOWN sorts as the coarsest (least trustworthy) of all.
    ORDER = (SECOND, MINUTE, HOUR, DAY, MONTH, YEAR, UNKNOWN)
    ALL = ORDER
    SUBDAY = (SECOND, MINUTE, HOUR)

    @classmethod
    def rank(cls, p: str) -> int:
        """Position in the fine→coarse order; unknown/invalid ranks as UNKNOWN."""
        try:
            return cls.ORDER.index(p)
        except ValueError:
            return cls.ORDER.index(cls.UNKNOWN)

    @classmethod
    def coarser(cls, a: str, b: str) -> str:
        """The less-precise of two precisions — never claim more than the weakest input."""
        return a if cls.rank(a) >= cls.rank(b) else b

    @classmethod
    def is_subday(cls, p: str) -> bool:
        """True when the precision resolves a time within a day (a clock time is real)."""
        return p in cls.SUBDAY


_RE_YEAR = re.compile(r"^\d{4}$")
_RE_MONTH = re.compile(r"^\d{4}-\d{1,2}$")
_RE_DAY = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
# The time portion of an ISO instant: capture H:M and whether seconds are present.
_RE_TIME = re.compile(r"[t ](\d{1,2}):(\d{2})(:(\d{2}))?", re.IGNORECASE)


def infer_precision(raw) -> str:
    """The precision a raw source value ACTUALLY carries — never an assumption.

    ``date`` → DAY. ``datetime`` → SECOND (an already-parsed instant is taken at face
    value; sub-second is not tracked). Strings are inspected: "2026" → YEAR,
    "2026-07" → MONTH, "2026-07-20" → DAY, "…T05:54:13" → SECOND, "…T05:54" → MINUTE.
    Anything unrecognized (or ``None``) → UNKNOWN.
    """
    if raw is None:
        return Precision.UNKNOWN
    if isinstance(raw, datetime):
        return Precision.SECOND
    if isinstance(raw, date):
        return Precision.DAY
    s = str(raw).strip()
    if not s:
        return Precision.UNKNOWN
    if _RE_YEAR.match(s):
        return Precision.YEAR
    if _RE_MONTH.match(s):
        return Precision.MONTH
    if _RE_DAY.match(s):
        return Precision.DAY
    m = _RE_TIME.search(s)
    if m:
        return Precision.SECOND if m.group(4) is not None else Precision.MINUTE
    return Precision.UNKNOWN


def _to_date(raw):
    """Best-effort calendar date for a coarse value. Returns (date | None, precision)."""
    if isinstance(raw, datetime):
        return raw.date(), Precision.SECOND
    if isinstance(raw, date):
        return raw, Precision.DAY
    if raw is None:
        return None, Precision.UNKNOWN
    s = str(raw).strip()
    prec = infer_precision(s)
    try:
        if prec == Precision.YEAR:
            return date(int(s), 1, 1), prec
        if prec == Precision.MONTH:
            y, mo = (int(p) for p in s.split("-")[:2])
            return date(y, mo, 1), prec
        if prec in (Precision.DAY, Precision.MINUTE, Precision.SECOND):
            # DAY string, or an ISO instant we fall back to the calendar date of.
            iso = s.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(iso).date(), prec
            except ValueError:
                y, mo, d = (int(p) for p in s[:10].split("-"))
                return date(y, mo, d), prec
    except (ValueError, TypeError):
        return None, Precision.UNKNOWN
    return None, Precision.UNKNOWN


def resolve_instant(value, fallback_date=None, now=None):
    """Turn a source value into ``(aware_datetime | None, precision)`` for storage.

    THE rule for writing any observed-moment timestamp:
      * A real sub-day instant (``datetime``, or an ISO string with a time) is stored
        verbatim at its true precision — nothing is invented.
      * A date-only / month / year value is placed on the calendar at local NOON of the
        (period-start) day, CLAMPED to no later than ``now`` so the stored instant can
        never be in the future, and its precision is reported as DAY/MONTH/YEAR so no
        consumer trusts the fabricated sub-precision part.
      * An unrecognized/absent value with no ``fallback_date`` → ``(None, UNKNOWN)``.

    ``value`` may be a ``datetime``, a ``date``, or a string. ``fallback_date`` is used
    only when ``value`` carries no date of its own.
    """
    now = now or timezone.now()

    # A real instant — preserve it (aware), precision SECOND. Future-sanity is the
    # surface's job (see temporal.py); we never discard a true measured time.
    if isinstance(value, datetime):
        dt = value if timezone.is_aware(value) else timezone.make_aware(value)
        return dt, Precision.SECOND

    day, prec = _to_date(value)
    # An ISO string WITH a time resolves to a real instant, not a fabricated noon.
    if prec in (Precision.MINUTE, Precision.SECOND) and not isinstance(value, date):
        try:
            iso = str(value).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            dt = dt if timezone.is_aware(dt) else timezone.make_aware(dt)
            return dt, prec
        except (ValueError, TypeError):
            pass  # fall through to date handling

    if day is None:
        day = fallback_date
        prec = Precision.DAY if day is not None else Precision.UNKNOWN
    if day is None:
        return None, Precision.UNKNOWN

    # Noon keeps the value on the correct calendar day across timezones; clamping to
    # ``now`` guarantees it is never in the future. Precision (DAY/MONTH/YEAR) is what
    # makes the fabricated sub-day part safe to ignore.
    noon = timezone.make_aware(datetime.combine(day, time(12, 0)))
    instant = min(noon, now)
    if prec == Precision.UNKNOWN:
        prec = Precision.DAY
    return instant, prec


def _relative_day(d, today):
    delta = (today - d).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if 1 < delta <= 6:
        return f"{delta} days ago"
    return None  # caller uses an absolute date


def format_instant(dt, precision, now=None) -> str:
    """Render a stored instant HONESTLY at its precision — never more than it knows.

    DAY → "Today" / "Yesterday" / "July 20" / "July 20, 2025".
    HOUR/MINUTE/SECOND → "Today • 5:54 AM" (a real clock time).
    MONTH → "July 2026".  YEAR → "2026".  UNKNOWN / no value → "date unknown".
    """
    if dt is None or precision == Precision.UNKNOWN:
        return "date unknown"
    now = now or timezone.now()
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    today = timezone.localdate(now) if timezone.is_aware(now) else now.date()

    if precision == Precision.YEAR:
        return local.strftime("%Y")
    if precision == Precision.MONTH:
        return local.strftime("%B %Y")

    if precision == Precision.DAY:
        rel = _relative_day(local.date(), today)
        if rel is not None:
            return rel
        stamp = local.strftime("%B %-d")
        return stamp if local.year == today.year else f"{stamp}, {local.year}"

    # Sub-day precision: a real clock time may be shown.
    day_label = _relative_day(local.date(), today)
    if day_label is None or day_label.endswith("ago"):
        day_label = local.strftime("%B %-d")
    if precision == Precision.HOUR:
        return f"{day_label} • {local.strftime('%-I %p')}"
    return f"{day_label} • {local.strftime('%-I:%M %p')}"  # MINUTE / SECOND
