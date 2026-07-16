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

from django.utils import timezone

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


def open_checkin_for_date(user, local_date):
    """The user's most-recent check-in whose local date is ``local_date``, or None.

    Used by every measurement/weigh-in write path (web, Chief of Staff, sync) to attach a
    new row to the day's open check-in, so a check-in is never left missing measurements
    the user logged the same day — regardless of which surface logged them. Must be called
    in a request context so ``checked_in_at__date`` truncates in the user's active tz.
    """
    from apps.health.models import BodyMeasurementSession

    return (
        BodyMeasurementSession.objects
        .filter(user=user, checked_in_at__date=local_date)
        .order_by("-checked_in_at")
        .first()
    )


def attach_measurement_to_open_checkin(entry):
    """Link an ungrouped BodyCompositionEntry to the same-day open check-in, if any.

    Idempotent (no-op when already grouped or no same-day check-in). Reversible — sets
    only the session FK; the measurement value is untouched (it remains canonical truth).
    Returns the session it linked to, or None.
    """
    if entry.session_id:
        return None
    session = open_checkin_for_date(entry.user, entry.measurement_date)
    if session is not None:
        entry.session = session
        entry.save(update_fields=["session"])
    return session


def associate_ungrouped_for_session(session):
    """Associate the user's currently-UNGROUPED measurements and weigh-ins recorded on
    the check-in's calendar date with this session.

    Workflow smoothing: when a user starts a check-in, the measurements and weight they
    already logged today (that aren't attached to any other session) clearly belong to
    it, so we group them automatically instead of making the user re-enter or manually
    link them. Deterministic and reversible — the session FK is SET_NULL and the
    measurement VALUES are never touched (the measurements remain the canonical truth;
    the session is only an organizational grouping). Only same-date, still-ungrouped rows
    are linked, so it never steals a measurement already assigned to another check-in.

    Returns ``(measurements_linked, weighins_linked)``.
    """
    from apps.health.models import BodyCompositionEntry, WeightEntry

    day = timezone.localtime(session.checked_in_at).date()
    measurements = BodyCompositionEntry.objects.filter(
        user=session.user, session__isnull=True, measurement_date=day
    ).update(session=session)
    weighins = WeightEntry.objects.filter(
        user=session.user, session__isnull=True, recorded_at__date=day
    ).update(session=session)
    return measurements, weighins


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
    # Weight can span far past 56 days — read a full-history light series (WeightEntry,
    # the canonical Weight domain) for every weight lens/graph. NEVER derive weight from
    # DailyHealthSummary here.
    weight_hist = _weight_history_series(user, target)
    trend_windows = _build_trend_windows(weight_hist, target)

    # ── Weight is CANONICAL everywhere in Body Intelligence ────────────────
    # BI CONSUMES the SAME Weight truth as the Weight page (build_weight_summary →
    # WeightEntry). It must NEVER show the DailyHealthSummary rollup's weight copy, which
    # can be stale or (pre-guard) contaminated. Body composition (fat/lean/quality) stays
    # from the rollup — that's its job — but every WEIGHT value below comes from the
    # Weight domain, so the snapshot, graph, and 14-day delta always match the Weight
    # page exactly. (Root cause of the "Body Intelligence still shows 51.0 lb" gap.)
    canonical_weight_lb = (weight or {}).get("current_lb")
    weight_chart_56d = [
        {"date": d.isoformat(), "value": v}
        for d, v in weight_hist if d >= lookback_56
    ]
    if body_comp is not None:
        body_comp["weight"] = canonical_weight_lb
        body_comp["weight_trend_56d"] = weight_chart_56d
        _wc14 = _window_change(weight_hist, 14, target)
        body_comp["weight_delta_14d"] = _wc14["delta"] if _wc14 else None

    # ── Measurement history series (per metric, for the graphs) ────────────
    measurement_series = _measurement_series(user, METRIC_LABELS)

    # ── Sessions: latest + previous applicable check-in ────────────────────
    sessions = _build_session_view(user)

    # ── Whole-journey body-composition direction (drives limb interpretation) ──
    # Baseline = first logged reading; classify the body's overall trajectory (fat/lean/
    # weight since the start of the journey), so a limb circumference is never judged alone.
    from apps.health.services.measurement_interpretation import (
        analyze_trajectory, build_body_assessment, build_insights,
    )
    _series = (measurement_series or {}).get("series", {})
    _weight_pts = [{"date": d.isoformat(), "value": v} for d, v in weight_hist] if weight_hist else []
    # ONE holistic assessment (overall + recent) — every card interpretation derives from it,
    # so the whole page tells the same story (no card conflicts with another).
    body_assessment = build_body_assessment(
        fat_traj=analyze_trajectory(_series.get("fat_mass"), "lb"),
        lean_traj=analyze_trajectory(_series.get("lean_mass"), "lb"),
        weight_traj=analyze_trajectory(_weight_pts, "lb"),
        bf_traj=analyze_trajectory(_series.get("body_fat_pct"), "pct"),
    )

    # ── Template-friendly rows — FACTS (overall + recent) then interpretation from the
    # single assessment. Insights are generated FROM these rows → guaranteed consistent. ──
    circumference_rows = _measurement_rows(snapshot, CIRCUMFERENCE_METRICS, METRIC_LABELS, measurement_series, body_assessment)
    composition_rows = _measurement_rows(snapshot, COMPOSITION_METRICS, METRIC_LABELS, measurement_series, body_assessment)
    insights = build_insights(circumference_rows + composition_rows)
    current = _current_snapshot(body_comp, snapshot, weight)
    current_cards = _current_snapshot_cards(current)

    # ── Deterministic headline (facts only) ────────────────────────────────
    headline = _build_headline(weight, goal, snapshot, body_comp)

    # ── Derived-truth freshness (Truth Presentation Contract, Dimension 2) ───
    # Body Intelligence trends/scores are DERIVED from DailyHealthSummary. If a
    # sync has persisted new data since the target-date summary was last built,
    # the derived layer is still catching up — surface that as "updating", never
    # as current. Facts only, consuming existing truth (summary.updated_at vs the
    # latest persistence event); one cheap indexed read, request-path safe.
    from apps.core.truth import lifecycle as _lifecycle
    _derived_at = getattr(today, "updated_at", None) if today else None
    _persisted_at = _latest_health_persistence_at(user)
    _fresh = _lifecycle.derived_state(persisted_at=_persisted_at, derived_at=_derived_at)
    freshness = {
        "state": _fresh["verdict"],                      # current | stale | pending
        "claim": _lifecycle.claim_key(_fresh["stage"], qualifier=_fresh["qualifier"]),
        "is_current": _fresh["stage"] == _lifecycle.CURRENT,
        "is_updating": _fresh["qualifier"] == _lifecycle.STALE,
        "derived_at": _derived_at.isoformat() if _derived_at else None,
        "persisted_at": _persisted_at.isoformat() if _persisted_at else None,
    }

    result = {
        "as_of": target,
        "headline": headline,
        "freshness": freshness,
        "snapshot": snapshot,
        "weight": weight,
        "goal": goal,
        "body_comp": body_comp,
        "trend_windows": trend_windows,
        "measurement_series": measurement_series,
        "circumference_rows": circumference_rows,
        "composition_rows": composition_rows,
        "body_assessment": body_assessment,
        "insights": insights,
        "current": current,
        "current_cards": current_cards,
        "sessions": sessions,
        "metric_labels": METRIC_LABELS,
        "circumference_metrics": CIRCUMFERENCE_METRICS,
        "composition_metrics": COMPOSITION_METRICS,
        "has_any_data": bool(snapshot or weight or (body_comp and body_comp.get("weight"))),
    }

    # ── "Your Body Story" — the executive interpretation over this evidence ──
    # One authoritative Chief-of-Staff briefing (Layer 1) composed deterministically from
    # the truth assembled above. The page renders it; the model still reasons over the
    # SAME truth in chat (via the facts-only page summary). No LLM on the request path.
    from apps.health.services.body_story_builder import build_body_story
    result["body_story"] = build_body_story(result)
    return result


# ── Internals ─────────────────────────────────────────────────────────────


def _latest_health_persistence_at(user):
    """Timestamp of the most recent health persistence event (Apple Health sync),
    used ONLY to detect whether DERIVED summaries have caught up with newly
    persisted data. Cheap: one indexed read over ``HealthIngestionRun``.
    Request-path safe. Returns None when the user has never synced."""
    from apps.mobile.models import HealthIngestionRun
    row = (HealthIngestionRun.objects
           .filter(user=user, status__in=("completed", "partial"))
           .order_by("-created_at")
           .values_list("completed_at", "created_at")
           .first())
    if not row:
        return None
    completed_at, created_at = row
    return completed_at or created_at


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


def _measurement_rows(snapshot, metric_order, metric_labels, measurement_series, body_assessment):
    """Ordered template rows for the metrics the user has logged, each interpreting its
    WHOLE journey — overall trend (baseline→now) + recent momentum — not a single delta.

    The verdict comes from ``measurement_interpretation`` (limb circumferences are read
    against the body's whole-journey ``body_assessment``, never in isolation). The current
    value comes straight from the canonical snapshot; the trend comes from the per-metric
    history series. No new queries.
    """
    from apps.health.services.measurement_interpretation import (
        analyze_trajectory, interpret_measurement,
    )

    if not snapshot:
        return []
    latest = snapshot.get("latest") or {}
    units = snapshot.get("units") or {}
    series_by_metric = (measurement_series or {}).get("series", {})

    rows = []
    for metric in metric_order:
        if metric not in latest:
            continue
        unit = units.get(metric, "")
        traj = analyze_trajectory(series_by_metric.get(metric), unit)
        interp = interpret_measurement(metric, unit, traj, body_assessment)
        rows.append({
            "metric": metric,
            "label": metric_labels.get(metric, metric),
            "value": latest.get(metric),
            "unit": unit,
            # Whole-journey interpretation — status/colour from the OVERALL trend (noise-
            # resistant); Overall + Recent trend text + a coach-style narrative.
            "status": interp["status"],              # improving | needs_attention | stable | inconclusive
            "status_label": interp["status_label"],
            "arrow": interp["arrow"],                # overall direction: up | down | flat
            "confidence": interp["confidence"],
            "overall_text": interp["overall_text"],  # "Down 6.2 in"
            "recent_text": interp["recent_text"],    # "Down 0.5 in"
            "evidence": interp["evidence"],          # body-composition context (limbs)
            "reason": interp["reason"],              # the interpretation narrative
            # Back-compat healthy-direction flag (kept for any older reader).
            "improved": True if interp["status"] == "improving" else (
                False if interp["status"] == "needs_attention" else None),
        })
    return rows


# ⚠️ ARCHITECTURAL INVARIANT — DO NOT "fix" body fat / fat mass / lean mass back to the
# DailyHealthSummary rollup (`body_comp`). That rollup only carries a value when a same-day
# rollup ran, so it reads None on most days and BLANKS composition that canonically exists.
# The Current Snapshot's authority is the latest-logged BodyCompositionEntry (`snapshot.latest`)
# — the same source Waist uses and the same numbers the "Body composition" section shows.
# One canonical producer per card, no rollup fallback. (Regression fixed 2026-07-14.)
def _current_snapshot(body_comp, snapshot, weight):
    """Named current values for the top snapshot cards — one consistent canonical authority.

    WEIGHT is the Weight domain (``build_weight_summary`` → ``WeightEntry``), the SAME
    source as the Weight page. Every BODY-COMPOSITION card — body fat, fat mass, lean mass,
    skeletal muscle, waist — reads the canonical latest-logged ``BodyCompositionEntry``
    snapshot (``snapshot.latest``), so the whole card row is internally consistent. A metric
    the user has never logged is absent from ``snapshot.latest`` → ``None`` → renders "—"
    (e.g. skeletal muscle, which has no canonical source yet). No rollup fallback, no merged
    sources, no fabricated value.
    """
    bc = body_comp or {}
    snap_latest = (snapshot or {}).get("latest") or {}
    snap_units = (snapshot or {}).get("units") or {}
    canonical_weight = (weight or {}).get("current_lb")
    return {
        # Weight is CANONICAL — the Weight domain (build_weight_summary → WeightEntry),
        # the SAME source as the Weight page. Never the DailyHealthSummary rollup.
        "weight": canonical_weight if canonical_weight is not None else bc.get("weight"),
        # Body composition — canonical latest-logged BodyCompositionEntry (snapshot.latest),
        # the SAME authority Waist uses. Never the DailyHealthSummary today-rollup (which is
        # None on any day without a same-day rollup, blanking values that canonically exist).
        "body_fat_pct": snap_latest.get("body_fat_pct"),
        "fat_mass": snap_latest.get("fat_mass"),
        "lean_mass": snap_latest.get("lean_mass"),
        "skeletal_muscle_mass": snap_latest.get("skeletal_muscle_mass"),
        "waist": snap_latest.get("waist"),
        "waist_unit": snap_units.get("waist", "in"),
    }


# ── Current Snapshot cards: value OR a read-only "why is this empty?" state ──
#
# A Current Snapshot card must never leave the user wondering whether the system is broken.
# It either shows the latest deterministic truth, or — when the user hasn't logged that
# metric yet — a read-only state that answers "why is this empty, and where does this value
# come from?". This is DETERMINISTIC PROVENANCE, not an action control: no buttons, no inline
# actions (the Current Snapshot stays a read-only executive summary). Applied uniformly to
# EVERY metric — never special-cased to one.

#: The Current Snapshot cards, in display order: (metric key, label, static unit | None).
#: A ``None`` unit means "resolve at render" (waist carries its own logged unit).
CURRENT_SNAPSHOT_CARDS = [
    ("weight", "Weight", "lb"),
    ("body_fat_pct", "Body Fat", "%"),
    ("fat_mass", "Fat Mass", "lb"),
    ("lean_mass", "Lean Mass", "lb"),
    ("skeletal_muscle_mass", "Skeletal Muscle", "lb"),
    ("waist", "Waist", None),
]

#: Per-metric provenance — the ONE place that answers "where does this value come from?" for
#: an unlogged card. Facts about WLJ's OWN ingestion, PLATFORM-NEUTRAL: the wording describes
#: the state of WLJ's truth, never one vendor's capabilities (a user may connect Apple Health,
#: Google Health Connect, Samsung Health, Fitbit, Garmin, Oura, Whoop, a direct integration, or
#: a future WLJ source). ``from_connected_source`` = whether ANY connected health source can
#: deliver this metric to WLJ today. Verified against the current sync handler map
#: (``apps/mobile/views.py`` ``process_health_metric``) + the manual Body Composition form:
#: weight / body fat / lean mass / waist can arrive from a connected source; ``fat_mass`` and
#: ``skeletal_muscle_mass`` cannot (no connected ecosystem exposes them — fat mass is derived,
#: skeletal muscle mass is not a standard synced quantity), so they are manual/CoS-only today.
#: ``entry_paths`` = the ways a user can supply the value TODAY.
CURRENT_SNAPSHOT_PROVENANCE = {
    "weight": {"from_connected_source": True, "entry_paths": ["Manual weigh-in", "Your Chief of Staff"]},
    "body_fat_pct": {"from_connected_source": True, "entry_paths": ["Manual Body Composition entry", "Your Chief of Staff"]},
    "fat_mass": {"from_connected_source": False, "entry_paths": ["Manual Body Composition entry", "Your Chief of Staff"]},
    "lean_mass": {"from_connected_source": True, "entry_paths": ["Manual Body Composition entry", "Your Chief of Staff"]},
    "skeletal_muscle_mass": {"from_connected_source": False, "entry_paths": ["Manual Body Composition entry", "Your Chief of Staff"]},
    "waist": {"from_connected_source": True, "entry_paths": ["Manual Body Composition entry", "Your Chief of Staff"]},
}


def _current_snapshot_cards(current):
    """Ordered, render-ready Current Snapshot cards.

    Each card is either POPULATED (``value`` is set → the template renders value + unit,
    unchanged from before) or EMPTY (``value is None`` → ``empty`` carries a deterministic,
    read-only explanation: a "Not yet logged" headline, a PLATFORM-NEUTRAL note about WLJ's
    current knowledge, and the entry paths that CAN supply it today). No per-metric
    special-casing; the same rule produces every card.
    """
    cur = current or {}
    cards = []
    for key, label, static_unit in CURRENT_SNAPSHOT_CARDS:
        value = cur.get(key)
        unit = static_unit if static_unit is not None else cur.get("waist_unit", "in")
        empty = None
        if value is None:
            prov = CURRENT_SNAPSHOT_PROVENANCE.get(
                key, {"from_connected_source": False, "entry_paths": []}
            )
            empty = {
                "headline": "Not yet logged",
                # We say "connected health source(s)" — NOT a vendor name — on purpose. This is
                # architectural: WLJ is intentionally platform-neutral. Apple Health, Google
                # Health Connect, Samsung Health, Garmin, Fitbit, Oura, Whoop, direct
                # integrations, and any future integration are all just "connected health
                # sources". The card describes WLJ's OWN current knowledge, not one ecosystem's
                # capabilities. The "…yet" phrasing keeps it forward-looking (a source may
                # provide it later).
                "source_note": (
                    "No reading available yet."
                    if prov["from_connected_source"]
                    else "No connected health source has provided this measurement yet."
                ),
                "entry_paths": prov["entry_paths"],
            }
        cards.append({
            "key": key,
            "label": label,
            "value": value,
            "unit": unit,
            "empty": empty,
        })
    return cards


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
