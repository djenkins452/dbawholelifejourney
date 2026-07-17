# ==============================================================================
# File: apps/health/services/health_dates.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The canonical health DATE contract — one definition, every consumer.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-17
# ==============================================================================
"""
Canonical health date contract (ONE definition — never re-implement it).

THE CONTRACT: a health date input identifies exactly ONE CALENDAR DAY. It accepts
  * a plain calendar date — "YYYY-MM-DD", or
  * an ISO-8601 instant   — "2026-07-16T17:33:35Z" / "2026-07-16T17:33:35+00:00"
    (an Apple HealthKit sample timestamp), which resolves to ITS calendar date,
  * a `date` / `datetime` object (already resolved),
and raises `ValueError` on anything else. Invalid input fails LOUDLY — it is never
guessed at.

NEVER SLICE THE STRING. `value[:10]` looks equivalent and is not: it *guesses* a date
out of text instead of parsing an instant, silently accepts malformed input, and would
bypass the timezone offset entirely. Parse it, or reject it.

WHY THIS MODULE EXISTS (production, 2026-07-17): this contract was already implemented
inside `apps/mobile/views.py :: process_health_metric` (the HealthKit ingest), but
`health.build_user_health_summary` had independently re-implemented it as
`strptime(value, "%Y-%m-%d")` — date-only. The iOS ingest path forwards the client's
raw ISO sample timestamp, so that task crashed with
`ValueError: unconverted data remains: T17:33:35Z`, while the backfill caller in
`apps/health/views.py` (which passes `str(date)`) succeeded — hence "adjacent
executions behave differently". The defect was TWO parsers for ONE contract. This
module is the single definition both now call; the contract was violated, never changed.

ATTRIBUTION NOTE (deliberate, do not "fix" casually): an instant resolves to its UTC
calendar date — `datetime.fromisoformat(...).date()` — which is EXACTLY how the ingest
attributes a HealthKit sample to a day. A summary rebuild MUST agree with the ingest,
or it would rebuild a different day than the records actually landed on. Whether that
UTC attribution (vs the user's local day) is the right truth is a SEPARATE question
about the ingest itself — changing it here alone would silently split the two apart.
"""
from datetime import date as _date
from datetime import datetime


def parse_health_date(value):
    """Resolve a health date input to a `datetime.date` per the canonical contract.

    Accepts "YYYY-MM-DD", an ISO-8601 instant ("…T…Z" / "…+00:00"), or an already
    resolved `date`/`datetime`. Raises `ValueError` on anything else.

    An instant resolves to its calendar date (UTC), matching how the ingest attributes
    a sample to a day. Never slices.
    """
    # `datetime` first — it subclasses `date`, so the order matters.
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, _date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid date format: {value!r}")

    raw = value.strip()
    try:
        if "T" in raw:
            # ISO-8601 instant — tolerate the "Z" military suffix fromisoformat()
            # does not accept on Python < 3.11.
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format: {value}")
