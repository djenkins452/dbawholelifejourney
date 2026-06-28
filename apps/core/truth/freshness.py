"""
Platform capability: FRESHNESS.

Domain-agnostic freshness verdicts for any Current Truth object. Beth READS the
verdict; she never infers it (Architecture Law 1). Implemented once here and
consumed by every domain:

    Health   — per-day steps/sleep/glucose/calories (first consumer)
    Finance  — account balances / snapshots via BankConnection.last_sync_at
    Faith    — last scripture read / reading-plan recency
    Calendar — event snapshot recency
    Relationships — interaction cadence recency

Two classifiers cover the two shapes of Current Truth:
- `classify_period_freshness` — a value FOR A SPECIFIC DAY/period (per-day truth).
- `classify_sync_freshness`   — a synced/snapshot value with a last-sync timestamp.

Both return one of the five canonical verdicts. `HONESTY_MARKERS` is the narration
contract each verdict must satisfy (kept in lockstep with the acceptance suite's
freshness questions).
"""

# Canonical verdicts -----------------------------------------------------------
CURRENT = "current"   # the value for the asked moment, complete → cite it
STALE = "stale"       # a real value, but older than asked → say "as of <when>"
PENDING = "pending"   # asked moment is now, data hasn't arrived yet → honest absence
PARTIAL = "partial"   # today, still accruing → say "so far"
MISSING = "missing"   # no value at all → honest absence

VERDICTS = (CURRENT, STALE, PENDING, PARTIAL, MISSING)

# Narration each verdict must satisfy (mirrors acceptance_rules freshness specs).
HONESTY_MARKERS = {
    STALE: ("as of", "from", "last synced", "earlier", "hasn't updated", "older"),
    PARTIAL: ("so far", "partial", "some", "incomplete", "still syncing",
              "only have", "not all"),
    PENDING: ("don't have", "haven't", "not yet", "hasn't synced", "no "),
    MISSING: ("don't have", "haven't", "no ", "not recorded"),
}


def classify_period_freshness(*, has_data, requested_date, data_date, today,
                              is_cumulative=False):
    """Freshness for a value tied to a specific day/period.

    Args:
        has_data: whether any value was found.
        requested_date: the day the user asked about (date).
        data_date: the day the found value belongs to (date or None).
        today: the user's local today (date).
        is_cumulative: True for metrics that keep accruing during the day
            (steps, calories) — a today value is PARTIAL, not CURRENT.
    """
    if not has_data:
        return PENDING if requested_date == today else MISSING
    if is_cumulative and requested_date == today:
        return PARTIAL
    if data_date is not None and requested_date is not None and data_date < requested_date:
        return STALE
    return CURRENT


def classify_sync_freshness(*, has_data, last_sync, now, stale_after_seconds):
    """Freshness for a synced/snapshot value (balances, CGM, connections).

    MISSING if there is no value or no sync; STALE once the last sync is older
    than `stale_after_seconds`; otherwise CURRENT.
    """
    if not has_data or last_sync is None:
        return MISSING
    if (now - last_sync).total_seconds() > stale_after_seconds:
        return STALE
    return CURRENT


def satisfies_honesty(verdict, text):
    """True if narration `text` carries a marker the verdict requires. CURRENT has
    no required marker (it simply cites the value). Used by acceptance/regression."""
    markers = HONESTY_MARKERS.get(verdict)
    if not markers:
        return True
    low = (text or "").lower()
    return any(m in low for m in markers)
