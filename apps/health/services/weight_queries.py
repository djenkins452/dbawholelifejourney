# ==============================================================================
# File: apps/health/services/weight_queries.py
# Layer 1 — Canonical WEIGHT retrieval for HISTORICAL TRUTH NAVIGATION (mirrors
# sleep_queries). Deterministic accessors over the weigh-in series — point-in-time,
# threshold crossing, extremum, and aggregate — so Beth can navigate history the way a
# Chief of Staff naturally would. One value per LOCAL day (the latest reading that day),
# matching `on_date` semantics. Never inferred, never a nearest-day substitute.
# ==============================================================================
from datetime import datetime, time, timedelta


def _user_tz(user):
    from django.utils import timezone as djtz
    try:
        from apps.core.utils import _get_user_tz
        return _get_user_tz(user)
    except Exception:
        return djtz.get_current_timezone()


def on_date(user, target_date):
    """The authoritative weight (lb) recorded on `target_date` (user-local day), or
    None. Uses a local-day datetime range so a late-evening reading is dated correctly."""
    from django.utils import timezone as djtz
    from apps.health.models import WeightEntry
    tz = _user_tz(user)
    start = djtz.make_aware(datetime.combine(target_date, time.min), tz)
    end = start + timedelta(days=1)
    e = (WeightEntry.objects.filter(user=user, recorded_at__gte=start, recorded_at__lt=end)
         .order_by("-recorded_at").first())
    if e is None:
        return None
    return {
        "date": target_date,
        "value_lb": round(float(e.value_in_lb), 1),
        "recorded_at": e.recorded_at,
        "unit": "lb",
    }


def series(user, start_date=None, end_date=None):
    """The weigh-in series (oldest → newest) as [{date, value_lb, recorded_at, unit}],
    ONE value per local day (the latest that day — same rule as on_date). `start_date` /
    `end_date` are inclusive local-day bounds (None = unbounded). Deterministic; the
    single source every navigation accessor reads."""
    from django.utils import timezone as djtz
    from apps.health.models import WeightEntry
    tz = _user_tz(user)
    qs = WeightEntry.objects.filter(user=user)
    if start_date is not None:
        qs = qs.filter(recorded_at__gte=djtz.make_aware(
            datetime.combine(start_date, time.min), tz))
    if end_date is not None:
        qs = qs.filter(recorded_at__lt=djtz.make_aware(
            datetime.combine(end_date, time.min), tz) + timedelta(days=1))
    by_day = {}
    for e in qs.order_by("recorded_at"):
        d = djtz.localtime(e.recorded_at, tz).date()
        by_day[d] = e                                     # ascending → latest that day wins
    out = []
    for d in sorted(by_day):
        e = by_day[d]
        out.append({"date": d, "value_lb": round(float(e.value_in_lb), 1),
                    "recorded_at": e.recorded_at, "unit": "lb"})
    return out


def first_crossing(user, threshold, direction):
    """The first day the weigh-in genuinely CROSSED `direction` ('below'/'above') the
    `threshold` (lb) — landing on the target side having been on the OTHER side the prior
    recorded day (a real transition, e.g. 301 → 299 for 'below 300'). If the series begins
    already on the target side (no transition recorded — data starts mid-journey), fall
    back to the earliest on-target day so the answer is still honest rather than a false
    'never'. Returns a record ({date, value_lb, ...}) or None if never on the target side."""
    def on_target(v):
        return v < threshold if direction == "below" else v > threshold

    def on_other(v):
        return v >= threshold if direction == "below" else v <= threshold

    s = series(user)
    prev = None
    for rec in s:
        v = rec["value_lb"]
        if on_target(v) and prev is not None and on_other(prev):
            return rec                                   # genuine crossing (transition)
        prev = v
    for rec in s:                                        # fallback: earliest on-target day
        if on_target(rec["value_lb"]):
            return rec
    return None


def extremum(user, kind, start_date=None, end_date=None):
    """The 'lowest' or 'highest' weigh-in in the window (inclusive), or None. Ties resolve
    to the EARLIEST such day (first time you reached it)."""
    s = series(user, start_date, end_date)
    if not s:
        return None
    best = s[0]
    for rec in s[1:]:
        if (kind == "lowest" and rec["value_lb"] < best["value_lb"]) or \
           (kind == "highest" and rec["value_lb"] > best["value_lb"]):
            best = rec
    return best


def average_over(user, start_date, end_date):
    """Mean weigh-in value across the window (inclusive), or None. One reading per day, so
    a day with three weigh-ins doesn't skew the mean. {avg_lb, n, start, end}."""
    s = series(user, start_date, end_date)
    if not s:
        return None
    vals = [r["value_lb"] for r in s]
    return {"avg_lb": round(sum(vals) / len(vals), 1), "n": len(vals),
            "start": start_date, "end": end_date, "unit": "lb"}
