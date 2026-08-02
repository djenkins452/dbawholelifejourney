# ==============================================================================
# File: apps/health/services/weight_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Weight overview facts — the SINGLE source shared by the
#              Weight page stats and the assistant's Current Context page summary.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""One deterministic Weight summary, consumed by BOTH the Weight page (WeightListView)
and the Current Context page-summary provider, so the assistant can never contradict the
numbers on screen (one source of truth — no re-derivation, no drift).

Request-path-safe: a handful of aggregate reads over the user's own WeightEntry rows.
"""
from datetime import timedelta

from django.utils import timezone

from apps.health.models import WeightEntry

# The rolling window for the "(30d)" stats the page shows. Genuine 30 DAYS (the label's
# promise), computed once here so page + assistant agree.
WINDOW_DAYS = 30


def build_weight_summary(user, *, point_date=None):
    """Deterministic Weight facts for `user`, or {} when there are no entries.

    Returns: current_lb/current_at, first_lb/first_at, total_change_lb, count,
    avg_30d_lb/low_30d_lb/high_30d_lb + window_count/window_days, and (optional)
    point_lb/point_at for a selected chart point. All weights are lb, rounded to 0.1.
    USER-SCOPED (the default manager already excludes soft-deleted rows)."""
    qs = WeightEntry.objects.filter(user=user)
    latest = qs.order_by("-recorded_at").first()
    if latest is None:
        return {}
    oldest = qs.order_by("recorded_at").first()
    count = qs.count()

    current_lb = round(float(latest.value_in_lb), 1)
    first_lb = round(float(oldest.value_in_lb), 1)
    single = oldest.pk == latest.pk

    window_start = timezone.now() - timedelta(days=WINDOW_DAYS)
    win_vals = [float(e.value_in_lb) for e in qs.filter(recorded_at__gte=window_start)]

    facts = {
        "current_lb": current_lb,
        "current_at": latest.recorded_at,
        "first_lb": first_lb,
        "first_at": oldest.recorded_at,
        "count": count,
        "total_change_lb": None if single else round(current_lb - first_lb, 1),
        "window_days": WINDOW_DAYS,
        "window_count": len(win_vals),
        "avg_30d_lb": round(sum(win_vals) / len(win_vals), 1) if win_vals else None,
        "low_30d_lb": round(min(win_vals), 1) if win_vals else None,
        "high_30d_lb": round(max(win_vals), 1) if win_vals else None,
    }

    # Optional selected point — a deterministic lookup of the entry on that calendar date.
    if point_date:
        pt = qs.filter(recorded_at__date=point_date).order_by("-recorded_at").first()
        if pt is not None:
            facts["point_lb"] = round(float(pt.value_in_lb), 1)
            facts["point_at"] = pt.recorded_at
    return facts


def build_weight_range_summary(user, *, range_key="all", today=None):
    """Deterministic Weight facts for ONE selected time range — the SINGLE source that
    drives the whole Weight page (graph + every stat + subtitle) AND the assistant's
    Current Context for that range. Every number here is derived from ONE filtered
    dataset so nothing on the page can disagree with anything else.

    The dataset is ``weight_queries.series`` (Layer-1 canonical: one value per local
    day, inclusive date bounds) filtered to the range's start date. Low/high/average/
    total-change and the subtitle endpoints are ALL computed from that same list —
    total change is first-visible → last-visible, exactly what the graph shows.

    Returns (all weights lb, rounded 0.1):
      range_key, range_label, range_suffix,
      has_range_data (any weigh-in inside the window),
      current_lb / current_at        — the true latest weigh-in (range-independent;
                                        the 'Latest' tile stays meaningful even when the
                                        window itself is empty),
      total_count                    — all-time entry count,
      count                          — weigh-ins (days) inside the window,
      first_lb / first_at            — first visible point in the window,
      last_lb / last_at              — last visible point in the window,
      low_lb / high_lb / avg_lb,
      total_change_lb                — last_lb − first_lb (None when < 2 points),
      chart_points                   — [{date, label, value, recorded_at}] oldest→newest,
                                        the EXACT list the stats were computed from.
    Returns {} only when the user has no weigh-ins at all.

    Request-path-safe: a bounded per-day series read over the user's own rows.
    """
    from django.utils import timezone as djtz

    from apps.core.trend_range import (
        normalize_range,
        range_label,
        range_start_date,
        range_suffix,
    )
    from apps.health.services import weight_queries

    range_key = normalize_range(range_key)

    true_latest = weight_queries.latest(user)
    if true_latest is None:
        return {}

    if today is None:
        try:
            from apps.core.utils import _get_user_tz
            tz = _get_user_tz(user)
        except Exception:
            tz = djtz.get_current_timezone()
        today = djtz.localtime(djtz.now(), tz).date()

    start_date = range_start_date(range_key, today)
    pts = weight_queries.series(user, start_date=start_date)  # ONE filtered dataset
    total_count = len(weight_queries.series(user)) if start_date is not None else len(pts)

    facts = {
        "range_key": range_key,
        "range_label": range_label(range_key),
        "range_suffix": range_suffix(range_key),
        "has_range_data": bool(pts),
        "current_lb": true_latest["value_lb"],
        "current_at": true_latest["recorded_at"],
        "total_count": total_count,
        "count": len(pts),
        "chart_points": [
            {
                "date": p["date"],
                "label": p["date"].strftime("%b %d, %Y"),
                "value": p["value_lb"],
                "recorded_at": p["recorded_at"].isoformat(),
            }
            for p in pts
        ],
    }

    if not pts:
        # Window empty (e.g. 3M selected but last weigh-in was months ago). Latest tile
        # stays honest; range-scoped stats are simply absent.
        facts.update({
            "first_lb": None, "first_at": None, "last_lb": None, "last_at": None,
            "low_lb": None, "high_lb": None, "avg_lb": None, "total_change_lb": None,
        })
        return facts

    vals = [p["value_lb"] for p in pts]
    first, last = pts[0], pts[-1]
    facts.update({
        "first_lb": first["value_lb"],
        "first_at": first["recorded_at"],
        "last_lb": last["value_lb"],
        "last_at": last["recorded_at"],
        "low_lb": round(min(vals), 1),
        "high_lb": round(max(vals), 1),
        "avg_lb": round(sum(vals) / len(vals), 1),
        "total_change_lb": None if len(pts) < 2 else round(last["value_lb"] - first["value_lb"], 1),
    })
    return facts
