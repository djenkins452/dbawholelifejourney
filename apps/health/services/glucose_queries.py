# ==============================================================================
# File: apps/health/services/glucose_queries.py
# Layer 1 — Canonical Glucose Reading Truth (latest + PREVIOUS).
#
# A Chief of Staff must distinguish the CURRENT reading from the PREVIOUS one and
# never silently substitute one for the other. WLJ surfaced only "latest", so
# "what was the previous glucose reading?" collapsed to the current value. This is
# the ONE deterministic accessor for both:
#
#   latest(user)   — the most recent reading (value, timestamp, source, freshness)
#   previous(user) — the reading IMMEDIATELY BEFORE latest, DISTINCT and EARLIER,
#                    plus its relation to the current reading. None when only one
#                    reading exists (there is no earlier reading — say so, never
#                    fall back to latest).
#
# Deterministic, read live from GlucoseEntry ordered by recorded_at (indexed). This
# is the reference implementation of "prior-reading truth"; BP / weight / any
# point-in-time reading follows the same shape. No consumer may re-derive "previous"
# by re-querying — read it here, so current and previous can never diverge.
# ==============================================================================
from datetime import timedelta

# A CGM/finger-stick reading older than this is no longer "current".
_STALE_AFTER_SECONDS = 6 * 3600

_FIELDS = ("value", "unit", "recorded_at", "source")


def _row_to_reading(row, now):
    from apps.core.truth.freshness import classify_sync_freshness
    ra = row["recorded_at"]
    fresh = classify_sync_freshness(has_data=True, last_sync=ra, now=now,
                                    stale_after_seconds=_STALE_AFTER_SECONDS)
    val = row["value"]
    try:
        val = float(val)
        val = int(val) if float(val).is_integer() else round(val, 1)
    except (TypeError, ValueError):
        pass
    return {
        "value": val,
        "unit": row.get("unit") or "mg/dL",
        "recorded_at": ra.isoformat() if ra is not None else None,
        "source": _source_label(row.get("source")),
        "freshness": fresh,
    }


_SOURCE_LABELS = {
    "dexcom": "your Dexcom CGM", "apple_health": "Apple Health",
    "manual": "a manual entry", "imported": "an imported record",
}


def _source_label(source):
    if not source:
        return "your glucose tracker"
    return _SOURCE_LABELS.get(str(source).lower(), str(source))


def _two_most_recent(user):
    from apps.health.models import GlucoseEntry
    return list(GlucoseEntry.objects.filter(user=user)
               .order_by("-recorded_at").values(*_FIELDS)[:2])


def _now(user):
    from django.utils import timezone
    return timezone.now()


def latest(user):
    """The most recent glucose reading, or None. Deterministic."""
    rows = _two_most_recent(user)
    if not rows:
        return None
    return _row_to_reading(rows[0], _now(user))


def previous(user):
    """The reading IMMEDIATELY BEFORE the latest — DISTINCT and EARLIER — with its
    relation to the current reading. Returns None when there is no earlier reading
    (only one reading on record): the caller must say so, never substitute latest."""
    now = _now(user)
    rows = _two_most_recent(user)
    if len(rows) < 2:
        return None
    cur = _row_to_reading(rows[0], now)
    prev = _row_to_reading(rows[1], now)
    prev["relation"] = _relation(cur, prev)
    return prev


def _relation(cur, prev):
    """How the previous reading relates to the current one: value delta, direction,
    and how long before the current reading it was taken. Deterministic."""
    from datetime import datetime
    rel = {"current_value": cur.get("value"), "current_unit": cur.get("unit")}
    try:
        cv, pv = float(cur["value"]), float(prev["value"])
        diff = round(cv - pv, 1)
        rel["delta"] = int(diff) if float(diff).is_integer() else diff
        rel["direction"] = ("rose" if diff > 0 else "fell" if diff < 0 else "held")
    except (TypeError, ValueError, KeyError):
        pass
    try:
        c = datetime.fromisoformat(cur["recorded_at"])
        p = datetime.fromisoformat(prev["recorded_at"])
        mins = int(round((c - p).total_seconds() / 60))
        if mins >= 0:
            rel["minutes_before_current"] = mins
    except (TypeError, ValueError, KeyError):
        pass
    return rel
