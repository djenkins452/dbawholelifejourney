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


# ── Sleep SCHEDULE CONSISTENCY (regularity of bedtime / wake / duration) ─────────
# The deterministic answer to "how consistent has my sleep schedule been" — the SPREAD of
# bedtime, wake-time and duration around their normal pattern (and whether that spread is
# tightening or loosening). Reuse-only: the authoritative-record-per-night selection above
# and the platform Consistency capability (apps.core.truth.consistency) which owns the
# midnight-safe circular statistics. Facts only — WLJ never says a schedule is good/bad.
_CONSISTENCY_FIELDS = ("sleep_date", "source", "bedtime", "wake_time",
                       "total_duration_minutes", "asleep_duration_minutes")


def _local_minute_of_day(dt, tz):
    """Minute-of-day (0..1439) of an aware datetime in the user's LOCAL clock — the value
    circular statistics need. Missing → None (never a fabricated midnight)."""
    if dt is None:
        return None
    try:
        loc = dt.astimezone(tz)
    except Exception:
        return None
    return loc.hour * 60 + loc.minute


def sleep_consistency(user, start_date, end_date, *, period_label=""):
    """THE single producer of sleep SCHEDULE-CONSISTENCY truth for nights whose `sleep_date`
    falls in [start_date, end_date]. One authoritative record per night (the SAME
    deterministic selection as `last_night`), each night's bedtime/wake converted to the
    user's LOCAL clock, then handed to the platform Consistency capability (circular for the
    clock fields, linear for duration). Returns a JSON-safe dict; `present` is False when
    fewer than two nights have the timing to measure a spread. Never fabricates a missing
    time as midnight."""
    from apps.core.truth.consistency import ConsistencyMetric
    from apps.core.utils import _get_user_tz
    from apps.health.models import SleepEntry

    try:
        tz = _get_user_tz(user)
    except Exception:
        from django.utils import timezone as _dtz
        tz = _dtz.get_current_timezone()

    by_night = {}
    for r in (SleepEntry.objects.filter(
            user=user, sleep_date__gte=start_date, sleep_date__lte=end_date)
            .values(*_CONSISTENCY_FIELDS)):
        d = r["sleep_date"]
        if d not in by_night or _rank(r) > _rank(by_night[d]):
            by_night[d] = r

    bed_pts, wake_pts, dur_pts = [], [], []
    for d in sorted(by_night):
        r = by_night[d]
        bm = _local_minute_of_day(r.get("bedtime"), tz)
        wm = _local_minute_of_day(r.get("wake_time"), tz)
        dur = _canonical_minutes(r)
        if bm is not None:
            bed_pts.append((d, float(bm)))
        if wm is not None:
            wake_pts.append((d, float(wm)))
        if dur is not None:
            dur_pts.append((d, float(dur)))

    fields = {
        "bedtime": ConsistencyMetric("sleep", "bedtime", "clock", "minutes",
                                     tuple(bed_pts)).to_dict(),
        "wake_time": ConsistencyMetric("sleep", "wake_time", "clock", "minutes",
                                       tuple(wake_pts)).to_dict(),
        "duration": ConsistencyMetric("sleep", "duration", "linear", "minutes",
                                      tuple(dur_pts)).to_dict(),
    }
    nights = len(by_night)
    present = any(f.get("present") for f in fields.values())
    return {
        "domain": "health", "metric": "sleep", "subject": "sleep",
        "period": period_label,
        "start": start_date.isoformat(), "end": end_date.isoformat(),
        "present": present,
        "nights_with_data": nights,
        "fields": fields,
    }


# ── Entity Completeness (record-level sleep detail for the Model Interface) ──────
# `describe`/`describe_one` return CompleteEntity objects exposing EVERY stored sleep
# dimension (stages, efficiency, quality, bedtime/waketime, HRV, respiratory rate…) —
# all stored on SleepEntry but previously unreachable (only hours were surfaced). One
# authoritative record per night (most recent row per sleep_date).
def _sleep_entity(e):
    from apps.core.truth.entity import CompleteEntity
    from apps.core.truth.freshness import CURRENT

    def _hrs(mins):
        return round(mins / 60.0, 2) if mins is not None else None

    def _f(v):
        return float(v) if v is not None else None

    g = lambda a: getattr(e, a, None)
    return CompleteEntity(
        kind="sleep",
        identity=f"Sleep — {e.sleep_date.isoformat()}",
        definition={
            "date": e.sleep_date.isoformat(),
            "bedtime": e.bedtime.isoformat() if g("bedtime") else None,
            "wake_time": e.wake_time.isoformat() if g("wake_time") else None,
            "source": g("source"),
        },
        status="logged",
        performance={
            "asleep_hours": _hrs(g("asleep_duration_minutes")),
            "in_bed_hours": _hrs(g("total_duration_minutes")),
            "deep_hours": _hrs(g("stage_deep_minutes")),
            "rem_hours": _hrs(g("stage_rem_minutes")),
            "light_hours": _hrs(g("stage_light_minutes")),
            "awake_hours": _hrs(g("stage_awake_minutes")),
            "total_awake_minutes": g("total_awake_minutes"),
            "efficiency_pct": _f(g("sleep_efficiency")),
            "quality_rating": g("quality_rating") or None,
            "quality_score": g("quality_score"),
            "interruptions": g("interruption_count"),
            "hrv_ms": _f(g("hrv_value")),
            "respiratory_rate": _f(g("respiratory_rate")),
            "heart_rate_avg": g("heart_rate_avg"),
            "heart_rate_min": g("heart_rate_min"),
            "heart_rate_max": g("heart_rate_max"),
            "vo2_max": _f(g("vo2_max")),
        },
        extensions={k: v for k, v in {
            "notes": g("notes") or None,
            "factors": g("factors") or None,
            "caffeine_mg": g("caffeine_mg"),
            "mindful_minutes": g("mindful_minutes"),
        }.items() if v is not None},
        freshness=CURRENT,
    )


def describe(user, *, since_days=30, limit=20):
    """Recent nights, each a CompleteEntity (one authoritative row per night)."""
    from apps.core.utils import get_user_today
    from apps.health.models import SleepEntry
    cutoff = get_user_today(user) - timedelta(days=since_days)
    seen, out = set(), []
    for e in (SleepEntry.objects.filter(user=user, sleep_date__gte=cutoff)
              .order_by("-sleep_date", "-id")):
        if e.sleep_date in seen:
            continue
        seen.add(e.sleep_date)
        out.append(_sleep_entity(e))
        if len(out) >= limit:
            break
    return out


def describe_one(user, name=None):
    """The most recent night as a CompleteEntity (name ignored — sleep has no label)."""
    from apps.health.models import SleepEntry
    e = SleepEntry.objects.filter(user=user).order_by("-sleep_date", "-id").first()
    return _sleep_entity(e) if e else None
