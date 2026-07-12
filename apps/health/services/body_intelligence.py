# ==============================================================================
# File: apps/health/services/body_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Read-only COMPOSITION of existing Body Intelligence truth for the
#              Body Intelligence dashboard, page summary, and CoS truth exposure.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-12
# ==============================================================================
"""Body Intelligence — the single read-only composition of the body-truth WLJ already
computes.

This service COMPOSES; it never RECOMPUTES. Every number it returns comes from an
existing deterministic authority:

* measurements latest-vs-previous  → ``body_composition_snapshot.build_body_composition_snapshot``
* weight overview facts            → ``weight_summary.build_weight_summary``
* weight-goal progress             → ``HealthProfile.get_weight_progress``
* body-composition intelligence    → ``HealthCommandCenterService._build_body_comp_panel``
                                       (fat-loss quality, plateau, recomposition,
                                        muscle preservation, 14-day deltas, 56-day
                                        trends, top insight — all pre-computed at
                                        daily-rollup time and read from
                                        ``DailyHealthSummary``)

The ONLY new arithmetic here is a single windowed-change helper (``_window_change``) —
one authority for "change over an arbitrary reporting lens" (weekly / monthly /
quarterly / yearly / YTD / custom). Those calendar windows are *reporting lenses over
historical truth*, never a storage or workflow model — Body Intelligence is
event-driven (a user checks in at any cadence).

Request-path-safe: pre-computed ``DailyHealthSummary`` reads + a handful of user-scoped
aggregate queries. No heavy compute, no LLM.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

#: Reporting lenses the dashboard offers. NOT a storage cadence — Body Intelligence is
#: event-driven; these are windows over history for "how has X changed over <period>?".
TREND_WINDOWS = [
    ("7d", "Past week", 7),
    ("30d", "Past month", 30),
    ("90d", "Past quarter", 90),
    ("365d", "Past year", 365),
]

#: Measurement metric_names that are body circumferences (tape measurements), in the
#: canonical display order. Uses WLJ's canonical names — ``arm_left`` / ``arm_right``,
#: never "bicep".
CIRCUMFERENCE_METRICS = [
    "neck", "shoulders", "chest", "waist", "hips",
    "arm_left", "arm_right", "forearm_left", "forearm_right",
    "thigh_left", "thigh_right", "calf_left", "calf_right",
]

#: Body-composition (non-circumference) metrics, canonical display order.
COMPOSITION_METRICS = [
    "body_fat_pct", "lean_mass", "fat_mass", "skeletal_muscle_mass",
    "bone_mass", "body_water_pct", "visceral_fat", "bmr", "metabolic_age", "bmi",
]


def build_body_intelligence(user, *, as_of=None):
    """Compose the full read-only Body Intelligence truth for ``user``.

    Returns a dict consumed by the dashboard view, the page-summary provider, and the
    CoS body-intelligence truth. Deterministic: same DB state → same dict.
    """
    from apps.health.models import (
        BodyCompositionEntry,
        BodyMeasurementSession,
        DailyHealthSummary,
        HealthProfile,
    )
    from apps.health.services.body_composition_snapshot import (
        METRIC_LABELS,
        build_body_composition_snapshot,
    )
    from apps.health.services.command_center_api import HealthCommandCenterService
    from apps.health.services.weight_summary import build_weight_summary

    target = as_of or date.today()

    # ── Measurements: canonical latest-vs-previous per metric ──────────────
    snapshot = build_body_composition_snapshot(user)

    # ── Weight overview facts + goal progress (canonical sources) ──────────
    weight = build_weight_summary(user) or {}
    goal = None
    try:
        profile = HealthProfile.objects.filter(user=user).first()
        if profile:
            goal = profile.get_weight_progress()
    except Exception:
        logger.warning("body_intelligence: weight-goal read failed", exc_info=True)

    # ── Body-composition intelligence (pre-computed, DailyHealthSummary) ───
    lookback_56 = target - timedelta(days=55)
    summaries = list(
        DailyHealthSummary.objects
        .filter(user=user, summary_date__gte=lookback_56, summary_date__lte=target)
        .order_by("summary_date")
    )
    today = next((s for s in reversed(summaries) if s.summary_date == target), None)
    recent_14 = summaries[-14:] if len(summaries) >= 14 else summaries
    body_comp = None
    try:
        body_comp = HealthCommandCenterService._build_body_comp_panel(
            summaries, recent_14, today
        )
    except Exception:
        logger.warning("body_intelligence: body-comp panel read failed", exc_info=True)

    # ── Trend lenses: windowed change over history (single authority) ──────
    weight_series = [
        (s.summary_date, float(s.weight)) for s in summaries if s.weight
    ]
    fat_series = [
        (s.summary_date, float(s.fat_mass)) for s in summaries if s.fat_mass
    ]
    lean_series = [
        (s.summary_date, float(s.lean_mass)) for s in summaries if s.lean_mass
    ]
    # Weight can span far past 56 days — read a full-history light series for the
    # yearly/YTD lens (values-only query, user-scoped).
    weight_hist = _weight_history_series(user, target)
    trend_windows = _build_trend_windows(weight_hist, target)

    # ── Measurement history series (per metric, for the graphs) ────────────
    measurement_series = _measurement_series(user, METRIC_LABELS)

    # ── Sessions: latest + previous applicable check-in ────────────────────
    sessions = _build_session_view(user)

    # ── Template-friendly flattened rows (arrangement of snapshot truth) ────
    circumference_rows = _measurement_rows(snapshot, CIRCUMFERENCE_METRICS, METRIC_LABELS)
    composition_rows = _measurement_rows(snapshot, COMPOSITION_METRICS, METRIC_LABELS)
    current = _current_snapshot(body_comp, snapshot, weight)

    # ── Deterministic headline (facts only) ────────────────────────────────
    headline = _build_headline(weight, goal, snapshot, body_comp)

    return {
        "as_of": target,
        "headline": headline,
        "snapshot": snapshot,
        "weight": weight,
        "goal": goal,
        "body_comp": body_comp,
        "trend_windows": trend_windows,
        "measurement_series": measurement_series,
        "circumference_rows": circumference_rows,
        "composition_rows": composition_rows,
        "current": current,
        "sessions": sessions,
        "metric_labels": METRIC_LABELS,
        "circumference_metrics": CIRCUMFERENCE_METRICS,
        "composition_metrics": COMPOSITION_METRICS,
        "has_any_data": bool(snapshot or weight or (body_comp and body_comp.get("weight"))),
    }


# ── Internals ─────────────────────────────────────────────────────────────


def _window_change(series, days, target):
    """The ONE authority for "change over a reporting window".

    ``series`` is a chronological list of ``(date, value)``. Returns
    ``{"start", "start_date", "end", "end_date", "delta"}`` comparing the latest point
    to the most recent point on-or-before ``target - days``, or ``None`` when there is
    no comparison point in the window. Pure arrangement of pre-computed values.
    """
    if not series:
        return None
    end_date, end_val = series[-1]
    cutoff = target - timedelta(days=days)
    start = None
    for d, v in series:
        if d <= cutoff:
            start = (d, v)
        else:
            break
    if start is None:
        return None
    start_date, start_val = start
    if start_date == end_date:
        return None
    return {
        "start": round(start_val, 2),
        "start_date": start_date,
        "end": round(end_val, 2),
        "end_date": end_date,
        "delta": round(end_val - start_val, 2),
    }


def _build_trend_windows(weight_series, target):
    """Weight change across each reporting lens (weekly/monthly/quarterly/yearly)."""
    windows = []
    for key, label, days in TREND_WINDOWS:
        change = _window_change(weight_series, days, target)
        windows.append({
            "key": key,
            "label": label,
            "days": days,
            "change": change,
        })
    return windows


def _weight_history_series(user, target, *, max_days=400):
    """Light, user-scoped weight series (lb) over the last ``max_days``, one point per
    day (latest that day), chronological. Arranges raw truth — no calculation."""
    from apps.health.models import WeightEntry

    since = target - timedelta(days=max_days)
    rows = list(
        WeightEntry.objects.filter(user=user, recorded_at__date__gte=since)
        .order_by("recorded_at")
        .values("recorded_at", "value", "unit")
    )
    by_day = {}
    for r in rows:
        d = r["recorded_at"].date()
        val = float(r["value"])
        if r["unit"] == "kg":
            val = val * 2.20462
        by_day[d] = round(val, 1)  # last wins → latest that day
    return sorted(by_day.items())


def _measurement_series(user, metric_labels):
    """Per-metric chronological ``[{date, value}]`` series for measurement graphs.

    One light user-scoped query; grouped in Python. Raw truth arranged for charting —
    the deltas the dashboard shows still come from the canonical snapshot.
    """
    from collections import defaultdict

    from apps.health.models import BodyCompositionEntry

    rows = list(
        BodyCompositionEntry.objects.filter(user=user)
        .order_by("measurement_date", "created_at")
        .values("metric_name", "value", "unit", "measurement_date")
    )
    series = defaultdict(list)
    units = {}
    for r in rows:
        series[r["metric_name"]].append({
            "date": r["measurement_date"].isoformat(),
            "value": float(r["value"]),
        })
        units[r["metric_name"]] = r["unit"] or ""
    return {
        "series": {k: v for k, v in series.items()},
        "units": units,
    }


def _build_session_view(user):
    """Latest and previous check-in summaries (organizational grouping only).

    Sessions are an organizational construct — the measurement deltas the dashboard
    shows come from the canonical per-metric snapshot, not from re-diffing sessions.
    """
    from apps.health.models import BodyMeasurementSession

    sessions = list(
        BodyMeasurementSession.objects.filter(user=user)
        .order_by("-checked_in_at")[:2]
    )
    if not sessions:
        return {"latest": None, "previous": None, "count": 0}

    def _summarize(s):
        return {
            "id": s.pk,
            "title": s.title or "Check-in",
            "checked_in_at": s.checked_in_at,
            "notes": s.notes,
            "source": s.get_source_display() if s.source else "",
            "measurement_count": s.measurement_count,
            "photo_count": s.photo_count,
        }

    total = BodyMeasurementSession.objects.filter(user=user).count()
    return {
        "latest": _summarize(sessions[0]),
        "previous": _summarize(sessions[1]) if len(sessions) > 1 else None,
        "count": total,
    }


def _measurement_rows(snapshot, metric_order, metric_labels):
    """Flatten the canonical snapshot into ordered template rows for the metrics in
    ``metric_order`` that the user has actually logged. Pure arrangement — every value
    comes straight from the snapshot; no re-diffing.
    """
    from apps.health.services.body_composition_snapshot import (
        METRIC_IMPROVEMENT_DIRECTION,
    )

    if not snapshot:
        return []
    latest = snapshot.get("latest") or {}
    previous = snapshot.get("previous") or {}
    delta = snapshot.get("delta") or {}
    delta_pct = snapshot.get("delta_pct") or {}
    units = snapshot.get("units") or {}

    rows = []
    for metric in metric_order:
        if metric not in latest:
            continue
        d = delta.get(metric)
        direction = METRIC_IMPROVEMENT_DIRECTION.get(metric, "none")
        improved = None
        if d is not None and direction != "none" and d != 0:
            moved_down = d < 0
            improved = (moved_down and direction == "down") or (
                not moved_down and direction == "up"
            )
        rows.append({
            "metric": metric,
            "label": metric_labels.get(metric, metric),
            "value": latest.get(metric),
            "unit": units.get(metric, ""),
            "previous": previous.get(metric),
            "delta": d,
            "delta_pct": delta_pct.get(metric),
            "improved": improved,
        })
    return rows


def _current_snapshot(body_comp, snapshot, weight):
    """Named current values for the top snapshot cards. Reads from the canonical sources
    (body-comp panel for weight/fat/lean, measurement snapshot for waist)."""
    bc = body_comp or {}
    snap_latest = (snapshot or {}).get("latest") or {}
    snap_units = (snapshot or {}).get("units") or {}
    return {
        "weight": bc.get("weight") if bc.get("weight") is not None else (weight or {}).get("current_lb"),
        "body_fat_pct": bc.get("body_fat_pct"),
        "fat_mass": bc.get("fat_mass"),
        "lean_mass": bc.get("lean_mass"),
        "skeletal_muscle_mass": bc.get("skeletal_muscle_mass"),
        "waist": snap_latest.get("waist"),
        "waist_unit": snap_units.get("waist", "in"),
    }


def _build_headline(weight, goal, snapshot, body_comp):
    """A deterministic one-glance answer to "what is happening to my body?".

    Facts only. The ONLY interpretive labels used are ones WLJ already computed at
    rollup time (``top_insight``, ``fat_loss_quality_label``) — this never invents a
    verdict. Returns ``{"primary", "supporting": [...]}``.
    """
    supporting = []

    # Weight movement (from canonical weight summary).
    primary = None
    if weight.get("total_change_lb") is not None:
        tc = weight["total_change_lb"]
        direction = "down" if tc < 0 else "up" if tc > 0 else "flat"
        primary = (
            f"Weight {('down' if tc < 0 else 'up')} "
            f"{abs(tc):g} lb overall (now {weight['current_lb']} lb)"
            if direction != "flat"
            else f"Weight holding at {weight['current_lb']} lb"
        )
    elif weight.get("current_lb") is not None:
        primary = f"Current weight {weight['current_lb']} lb"

    # Pre-computed intelligence insight (already deterministic).
    if body_comp:
        if body_comp.get("top_insight"):
            supporting.append(body_comp["top_insight"])
        elif body_comp.get("fat_loss_quality_label"):
            supporting.append(
                f"Fat-loss quality: {body_comp['fat_loss_quality_label'].replace('_', ' ').title()}"
            )

    # Biggest measurement win (from canonical snapshot).
    if snapshot and snapshot.get("largest_improvement"):
        imp = snapshot["largest_improvement"]
        unit = (snapshot.get("units") or {}).get(imp["metric"], "")
        sign = "+" if imp["delta"] > 0 else ""
        supporting.append(f"Biggest change: {imp['label']} {sign}{imp['delta']:g}{unit}")

    # Goal progress (from canonical goal calc).
    if goal and goal.get("progress_percent") is not None and goal.get("goal") is not None:
        supporting.append(
            f"Goal {goal['goal']:g} {goal.get('unit', 'lb')}: "
            f"{goal['progress_percent']:g}% there"
        )

    if primary is None:
        primary = "Log a measurement or weigh-in to start tracking your body."
    return {"primary": primary, "supporting": supporting}
