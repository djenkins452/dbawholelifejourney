# ==============================================================================
# File: apps/health/services/sleep_queries.py
# Layer 1 — Canonical Sleep Truth.
#
# ONE deterministic source of truth for "last night's sleep" and recent sleep,
# read LIVE from SleepEntry. Every consumer (SAE → dashboard → Beth) reads THIS,
# so they cannot silently diverge from each other or from what the user sees in
# Apple Health. Origin: a truth-lineage divergence — Apple Health showed a night
# as 6 hr 9 min while WLJ reported 4.8 hr for the SAME night, because the SAE
# picked a record NON-DETERMINISTICALLY (`.first()` over `-sleep_date`) and read
# the WRONG duration field (`total_duration_minutes` = time in bed) instead of the
# metric Apple actually displays (time asleep).
#
# Two — and only two — intentional, DOCUMENTED, deterministic transformations:
#
#   1. DURATION METRIC = TIME ASLEEP. Apple Health's headline "Sleep" figure is
#      Time Asleep. SleepEntry stores BOTH `total_duration_minutes` (time in bed)
#      and `asleep_duration_minutes` (time asleep). To agree with what the user
#      sees, the canonical duration is `asleep_duration_minutes` when present,
#      else `total_duration_minutes` (manual / legacy rows that never populated
#      asleep). This is the ONLY value transformation and it is tested.
#
#   2. AUTHORITATIVE RECORD per night. A night can have more than one SleepEntry
#      (multiple devices/sources, or a nap). The canonical record for a night is
#      chosen DETERMINISTICALLY — source precedence (wearables over manual), then
#      the most-complete (largest duration) — never an arbitrary `.first()`. The
#      same night resolves to the same record for every consumer.
#
# No consumer may silently change the value. Any consumer wanting sleep duration
# reads `last_night()` / `recent_average_hours()`.
# ==============================================================================
from datetime import timedelta

# Higher = more authoritative for the same night. Wearables measure sleep; a
# manual entry is a best-effort estimate, so it loses to a device reading.
_SOURCE_PRECEDENCE = {
    "apple_health": 100, "oura": 95, "whoop": 95, "garmin": 90, "fitbit": 90,
    "google_fit": 85, "samsung_health": 85, "other": 50, "manual": 10,
}


def _canonical_minutes(row):
    """Transformation #1 — TIME ASLEEP (Apple's headline metric), falling back to
    time-in-bed only when asleep was never recorded. `row` is a values() dict."""
    asleep = row.get("asleep_duration_minutes")
    if asleep is not None and asleep > 0:
        return int(asleep)
    total = row.get("total_duration_minutes")
    return int(total) if total else None


def _rank(row):
    """Transformation #2 — deterministic authority: source precedence, then the
    most-complete reading. Total ordering, so ties never resolve arbitrarily."""
    return (_SOURCE_PRECEDENCE.get(row.get("source") or "other", 50),
            _canonical_minutes(row) or 0)


_FIELDS = ("sleep_date", "source", "total_duration_minutes",
           "asleep_duration_minutes", "quality_score")


def _night_for_date(user, target_date):
    """The AUTHORITATIVE sleep record for a SPECIFIC night (``sleep_date ==
    target_date``), using the SAME deterministic selection (source precedence, most
    complete) and canonical time-asleep metric as ``last_night``. Returns the night
    dict, or ``None`` when there is no data for that night."""
    from apps.health.models import SleepEntry
    rows = [r for r in SleepEntry.objects.filter(user=user, sleep_date=target_date)
            .values(*_FIELDS) if _canonical_minutes(r) is not None]
    if not rows:
        return None
    best = max(rows, key=_rank)
    mins = _canonical_minutes(best)
    try:
        from apps.core.utils import get_user_today
        days = (get_user_today(user) - target_date).days
    except Exception:
        days = 0
    return {
        "date": target_date,
        "minutes": mins,
        "hours": round(mins / 60, 1),
        "source": best.get("source"),
        "in_bed_minutes": best.get("total_duration_minutes"),
        "asleep_minutes": best.get("asleep_duration_minutes"),
        "quality": best.get("quality_score"),
        "freshness": "current" if days <= 1 else "stale",
        "record_count": len(rows),
    }


def on_date(user, target_date):
    """Deterministic POINT-IN-TIME sleep retrieval — the night whose WAKE date is
    ``target_date`` (SleepEntry.sleep_date). Same canonical truth as ``last_night``,
    for any historical night. Returns ``None`` when there is no record for that night
    — callers must say so honestly and NEVER infer or substitute another night."""
    return _night_for_date(user, target_date)


def last_night(user):
    """The AUTHORITATIVE sleep record for the most recent night, deterministically.

    Returns ``{date, minutes, hours, source, in_bed_minutes, asleep_minutes,
    quality, freshness, record_count}`` or ``None`` when there is no sleep data.
    `hours` is the canonical (time-asleep) duration — the same value every
    consumer sees."""
    from apps.health.models import SleepEntry
    latest = (SleepEntry.objects.filter(user=user)
              .order_by("-sleep_date")
              .values_list("sleep_date", flat=True).first())
    if latest is None:
        return None
    return _night_for_date(user, latest)


def recent_average_hours(user, days=7):
    """7-night average of the canonical per-night duration — ONE authoritative
    record per night (same metric + selection as ``last_night``), so the average
    and the nightly value can never be computed from different truths. Returns
    hours (float) or None."""
    from apps.health.models import SleepEntry
    try:
        from apps.core.utils import get_user_today
        cutoff = get_user_today(user) - timedelta(days=days)
    except Exception:
        return None
    by_night = {}
    for r in (SleepEntry.objects.filter(user=user, sleep_date__gte=cutoff)
              .values(*_FIELDS)):
        if _canonical_minutes(r) is None:
            continue
        d = r["sleep_date"]
        if d not in by_night or _rank(r) > _rank(by_night[d]):
            by_night[d] = r
    if not by_night:
        return None
    total = sum(_canonical_minutes(r) for r in by_night.values())
    return round((total / len(by_night)) / 60, 1)
