# ==============================================================================
# File: apps/ai/chatgpt_cos/date_reference.py
# Shared deterministic DATE-REFERENCE resolver for point-in-time entity retrieval.
# Makes Layer 1 entities queryable "by point in time" the same way across domains
# (Medication → Sleep → Weight → Workout): parse an explicit/relative date expression
# in a message to a concrete date, or None. No inference — the caller retrieves the
# canonical record for that exact date and says so honestly when there is none.
#
# Resolves (against the user's local TODAY): explicit M/D, M/D/Y, "July 1",
# ISO 2026-07-01; N days/nights ago; day before yesterday (today−2); yesterday
# (today−1); optionally today; last <weekday> / <weekday> (most recent past).
# ==============================================================================
import logging
import re
from datetime import date, timedelta

logger = logging.getLogger(__name__)

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


def user_today(user):
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


def resolve_reference_date(user, message, *, include_today=False):
    """Resolve a date expression in `message` to a concrete date, or None when there is
    no explicit/relative date reference (so the caller's 'current' path keeps its job)."""
    n = (message or "").lower()
    try:
        today = user_today(user)
    except Exception:
        logger.warning("date_reference: today failed", exc_info=True)
        return None

    m = _ISO_RE.search(n)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _MD_RE.search(n)
    if m:
        yr = int(m.group(3)) if m.group(3) else None
        return _most_recent_past(int(m.group(1)), int(m.group(2)), today, yr)
    m = _MONTH_RE.search(n)
    if m:
        yr = int(m.group(3)) if m.group(3) else None
        return _most_recent_past(_MONTHS[m.group(1)[:3]], int(m.group(2)), today, yr)
    m = _NAGO_RE.search(n)
    if m:
        tok = m.group(1)
        num = int(tok) if tok.isdigit() else _NUMWORDS.get(tok, 0)
        return today - timedelta(days=num) if num else None
    if "day before yesterday" in n:
        return today - timedelta(days=2)
    if "yesterday" in n:
        return today - timedelta(days=1)
    if include_today and any(p in n for p in ("today", "tonight", "this morning")):
        return today
    for name, wd in _WEEKDAYS.items():
        if name in n:
            delta = (today.weekday() - wd) % 7
            if delta == 0:            # same weekday → the most recent PAST one
                delta = 7
            return today - timedelta(days=delta)
    return None


def fmt_date(d):
    """"Tuesday, July 1" without platform-specific %-d."""
    return f"{d.strftime('%A, %B')} {d.day}"
