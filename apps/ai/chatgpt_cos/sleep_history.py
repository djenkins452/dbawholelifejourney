# ==============================================================================
# File: apps/ai/chatgpt_cos/sleep_history.py
# Capability: HISTORICAL SLEEP RETRIEVAL (Sleep Entity Completeness).
#
# Sleep truth already exists per night (SleepEntry, keyed by wake date); the gap was
# RETRIEVAL — every sleep question returned "last night" regardless of the point in
# time asked about ("What did I sleep on 7/1?" → last night). Modelled on Medication
# Entity Completeness: make sleep fully queryable BY POINT IN TIME, deterministically.
#
# This module owns only (a) resolving a point-in-time expression in the message to a
# concrete WAKE date, and (b) narrating the canonical record for that night. The truth
# itself comes from apps.health.services.sleep_queries.on_date — one canonical source,
# no re-derivation. It NEVER infers or summarizes: if there is no record for the night
# asked about, it says so.
#
# A night is identified by its WAKE date (SleepEntry.sleep_date). Relative expressions
# resolve against the user's local TODAY:
#   last night        → (declined here — the existing "current" path owns it)
#   yesterday / the night before / night before last / previous night → today − 1
#   two nights ago    → today − 2       N nights/days ago → today − N
#   last <weekday> / <weekday> → most recent past date with that weekday
#   explicit M/D, M/D/Y, "July 1", ISO 2026-07-01 → that exact date
# ==============================================================================
import logging
import re
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_SLEEP_CUES = ("sleep", "slept", "sleeping")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}
_NUMWORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
             "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

_MD_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(\d{4}))?\b")
_NAGO_RE = re.compile(
    r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:nights?|days?)\s+ago\b")


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


def _most_recent_past(month, day, today, year=None):
    """The date for month/day that is the most recent one NOT after today (this year,
    else last year — so '12/25' asked in July resolves to last December)."""
    if year is not None:
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    for y in (today.year, today.year - 1):
        try:
            cand = date(y, month, day)
        except ValueError:
            continue
        if cand <= today:
            return cand
    return None


def resolve_night_date(user, message):
    """Resolve a HISTORICAL point-in-time expression to a concrete wake date, or None.

    Returns None for "last night"/"tonight"/no reference, so the existing current-night
    path keeps answering those (protects existing behavior)."""
    n = (message or "").lower()
    try:
        today = _today(user)
    except Exception:
        logger.warning("sleep_history: today failed", exc_info=True)
        return None

    # ISO date (most specific).
    m = _ISO_RE.search(n)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # M/D or M/D/Y.
    m = _MD_RE.search(n)
    if m:
        yr = int(m.group(3)) if m.group(3) else None
        return _most_recent_past(int(m.group(1)), int(m.group(2)), today, yr)
    # Month name + day.
    m = _MONTH_RE.search(n)
    if m:
        yr = int(m.group(3)) if m.group(3) else None
        return _most_recent_past(_MONTHS[m.group(1)[:3]], int(m.group(2)), today, yr)
    # N nights/days ago.
    m = _NAGO_RE.search(n)
    if m:
        tok = m.group(1)
        num = int(tok) if tok.isdigit() else _NUMWORDS.get(tok, 0)
        return today - timedelta(days=num) if num else None
    # "two nights ago" phrased without a digit already handled above via numwords.
    # Named relatives → the night before last night (today − 1).
    if any(p in n for p in ("night before last", "the night before", "previous night",
                            "night before")):
        return today - timedelta(days=1)
    if "day before yesterday" in n:
        return today - timedelta(days=2)
    if "yesterday" in n:
        return today - timedelta(days=1)
    # Weekday ("last monday", "monday", "this past tuesday").
    for name, wd in _WEEKDAYS.items():
        if name in n:
            delta = (today.weekday() - wd) % 7
            if delta == 0:            # same weekday → the most recent PAST one
                delta = 7
            return today - timedelta(days=delta)
    return None


def _fmt(d):
    # "Tuesday, July 1" without platform-specific %-d.
    return f"{d.strftime('%A, %B')} {d.day}"


def _compose(night, target_date):
    if night is None:
        return (f"I don't have a sleep record for {_fmt(target_date)}. "
                "Nothing synced for that night.")
    parts = [f"On {_fmt(target_date)} you slept {night['hours']} hours"]
    q = night.get("quality")
    if q:
        parts.append(f" (sleep score {int(q)})")
    return "".join(parts) + "."


def answer(user, message, conversation=None):
    """If the message asks about SLEEP at a specific/historical point in time, retrieve
    that exact night deterministically. Declines (None) for non-sleep questions and for
    "last night"/current questions (handled by the existing path)."""
    n = (message or "").lower()
    if not any(c in n for c in _SLEEP_CUES):
        return None
    target = resolve_night_date(user, message)
    if target is None:
        return None
    try:
        from apps.health.services.sleep_queries import on_date
        night = on_date(user, target)
    except Exception:
        logger.warning("sleep_history: retrieval failed", exc_info=True)
        return None
    return {"answer": _compose(night, target), "tools_called": [],
            "tools_advertised": [], "lane": "sleep_history",
            "sleep_date": target.isoformat()}
