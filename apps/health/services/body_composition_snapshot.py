# ==============================================================================
# File: apps/health/services/body_composition_snapshot.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical body composition snapshot — latest vs previous, deltas,
#              trend interpretation. Read-only, deterministic, no LLM.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-07
# ==============================================================================
"""
Body Composition Snapshot — deterministic canonical state for Beth + SAE.

Beth must NEVER directly query body composition tables. Beth consumes this
service's output via the SAE ``health.body_composition`` snapshot, or via
the body-composition adapter exposed through the existing EventResolver
contract. The trust contract:

    If the data exists in WLJ, Beth can reason over it.

This service answers three classes of questions deterministically:

1. **Current**       — "What is my waist? My chest? My latest measurements?"
2. **Comparative**   — "What changed since last time? Compare to previous."
3. **Interpretive**  — "Where am I improving? Am I preserving muscle?"

Comparison rule (locked):
    latest measurement date  vs  most recent PRIOR measurement date

NOT average. NOT all-time. NOT some rolling window. Literal latest vs
previous — the same comparison the user themselves would do by eye.

Per-metric noise thresholds keep tape/scale noise out of the trend summary
but are NEVER applied to the raw delta — the user always sees the literal
number; thresholds only gate the human-readable "Trending down" verdicts.

NOT the same scope as ``body_composition_intelligence.py`` — that service
handles fat-loss-quality / plateau / muscle-loss-risk classification at
daily-rollup time. This snapshot answers "what changed since last time?"
deterministically, with zero LLM.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

logger = logging.getLogger(__name__)


# ── Display & semantics tables ─────────────────────────────────────────

#: Human-readable label per metric_name.
METRIC_LABELS = {
    "waist": "Waist",
    "chest": "Chest",
    "hips": "Hips",
    "neck": "Neck",
    "shoulders": "Shoulders",
    "arm_left": "Arm (Left)",
    "arm_right": "Arm (Right)",
    "forearm_left": "Forearm (Left)",
    "forearm_right": "Forearm (Right)",
    "thigh_left": "Thigh (Left)",
    "thigh_right": "Thigh (Right)",
    "calf_left": "Calf (Left)",
    "calf_right": "Calf (Right)",
    "body_fat_pct": "Body Fat %",
    "lean_mass": "Lean Mass",
    "fat_mass": "Fat Mass",
    "skeletal_muscle_mass": "Skeletal Muscle Mass",
    "bone_mass": "Bone Mass",
    "body_water_pct": "Body Water %",
    "visceral_fat": "Visceral Fat",
    "bmr": "BMR",
    "metabolic_age": "Metabolic Age",
    "bmi": "BMI",
}

#: For each metric, the DIRECTION that represents a body-composition
#: improvement (per the user's stated goals: weight loss, muscle
#: preservation, metabolic health). Strict deterministic mapping — no
#: fabricated "good news" anywhere. Metrics not in the table use
#: ``"none"`` (neutral — no win/regression framing).
METRIC_IMPROVEMENT_DIRECTION = {
    # Circumference/composition losses that signal fat loss:
    "waist": "down",
    "hips": "down",
    "thigh_left": "down",
    "thigh_right": "down",
    "body_fat_pct": "down",
    "fat_mass": "down",
    "visceral_fat": "down",
    "bmi": "down",
    "metabolic_age": "down",
    # Mass preservation / growth signals (during weight loss):
    "lean_mass": "up",
    "skeletal_muscle_mass": "up",
    "bone_mass": "up",
    # Neutral — direction depends on phase; never auto-classified.
    "body_water_pct": "none",
    "chest": "none",
    "neck": "none",
    "shoulders": "none",
    "arm_left": "none",
    "arm_right": "none",
    "forearm_left": "none",
    "forearm_right": "none",
    "calf_left": "none",
    "calf_right": "none",
    "bmr": "none",
}

#: Per-metric noise threshold for the trend-summary verbiage. Raw deltas
#: are reported as-is; only the human verdict ("Trending down" / "Stable")
#: respects this threshold so tape-measure jitter doesn't read as progress.
TREND_NOISE_THRESHOLD = {
    "waist": 0.25,
    "chest": 0.25,
    "hips": 0.25,
    "neck": 0.25,
    "shoulders": 0.25,
    "arm_left": 0.20,
    "arm_right": 0.20,
    "forearm_left": 0.20,
    "forearm_right": 0.20,
    "thigh_left": 0.30,
    "thigh_right": 0.30,
    "calf_left": 0.20,
    "calf_right": 0.20,
    "body_fat_pct": 0.5,
    "lean_mass": 0.5,
    "fat_mass": 0.5,
    "skeletal_muscle_mass": 0.5,
    "bone_mass": 0.1,
    "body_water_pct": 0.5,
    "visceral_fat": 0.5,
    "bmr": 25,
    "metabolic_age": 1,
    "bmi": 0.1,
}

#: Days after which the latest measurement is considered "stale" for
#: the snapshot freshness flag.
STALE_AFTER_DAYS = 60


# ── Public API ──────────────────────────────────────────────────────────


def build_body_composition_snapshot(user) -> dict | None:
    """Build the canonical body composition snapshot for ``user``.

    Returns ``None`` when the user has no BodyCompositionEntry rows at all —
    consumer renders the "no measurements logged yet" state in that case.
    Returns a populated dict in every other case, even when only one
    historical row exists for any metric (delta is ``None`` for those —
    never fabricated).

    Output shape (consumed by SAE health state + Beth body-comp adapter):

        {
          "latest_date":          date | None,
          "previous_date":        date | None,
          "days_between":         int  | None,
          "latest":   {metric_name: float, ...},
          "previous": {metric_name: float, ...},   # value at the
                                                   # PREVIOUS DATE for
                                                   # each metric, or None
          "units":    {metric_name: str,   ...},   # unit at LATEST entry
          "delta":    {metric_name: float | None, ...},
          "delta_pct":{metric_name: float | None, ...},
          "metric_labels": {metric_name: human_label},
          "largest_improvement": {metric, delta, label} | None,
          "largest_regression":  {metric, delta, label} | None,
          "trend_summary": [human-readable verdict, ...],
          "sync_stale": bool,
          "total_metrics_tracked": int,
        }

    Determinism: same DB state → same dict. Read-only.
    """
    from apps.health.models import BodyCompositionEntry

    rows = list(
        BodyCompositionEntry.objects.filter(user=user)
        .order_by("-measurement_date", "-created_at")
        .values("metric_name", "value", "unit", "measurement_date")
    )

    if not rows:
        return None

    # Group by metric → list of (date, value, unit), newest first.
    by_metric: dict[str, list[tuple[date, float, str]]] = defaultdict(list)
    for r in rows:
        by_metric[r["metric_name"]].append(
            (r["measurement_date"], float(r["value"]), r["unit"] or ""),
        )

    latest_overall = max(r["measurement_date"] for r in rows)

    # Per metric: latest = first entry; previous = most recent entry
    # whose date is STRICTLY EARLIER than the latest's date. This
    # implements the literal "latest vs previous" rule — never
    # "newest two rows in storage order."
    latest_map: dict[str, float] = {}
    previous_map: dict[str, float | None] = {}
    units_map: dict[str, str] = {}
    delta_map: dict[str, float | None] = {}
    delta_pct_map: dict[str, float | None] = {}
    previous_date_per_metric: dict[str, date] = {}

    for metric, entries in by_metric.items():
        latest_date, latest_val, latest_unit = entries[0]
        latest_map[metric] = round(latest_val, 2)
        units_map[metric] = latest_unit
        prior = next(
            (e for e in entries[1:] if e[0] < latest_date), None
        )
        if prior is None:
            previous_map[metric] = None
            delta_map[metric] = None
            delta_pct_map[metric] = None
            continue
        prev_date, prev_val, _ = prior
        previous_map[metric] = round(prev_val, 2)
        previous_date_per_metric[metric] = prev_date
        delta = round(latest_val - prev_val, 2)
        delta_map[metric] = delta
        if prev_val != 0:
            delta_pct_map[metric] = round((delta / prev_val) * 100, 1)
        else:
            delta_pct_map[metric] = None

    # Top-level previous_date = the OLDEST per-metric previous_date among
    # the metrics measured TODAY (the latest batch). This makes
    # "compare now to last time" canonical and stable: when the user
    # logs the same set of metrics each session, this collapses to
    # the prior session's date.
    previous_dates_for_latest_batch = [
        previous_date_per_metric[m]
        for m, entries in by_metric.items()
        if entries[0][0] == latest_overall and m in previous_date_per_metric
    ]
    previous_date = (
        min(previous_dates_for_latest_batch)
        if previous_dates_for_latest_batch else None
    )
    days_between = (
        (latest_overall - previous_date).days
        if previous_date else None
    )

    largest_improvement = None
    largest_regression = None
    for metric, delta in delta_map.items():
        if delta is None:
            continue
        direction = METRIC_IMPROVEMENT_DIRECTION.get(metric, "none")
        if direction == "none":
            continue
        # "improvement_magnitude" — signed so the strictly-positive value
        # is always an improvement and strictly-negative is a regression.
        signed_improvement = -delta if direction == "down" else delta
        rec = {
            "metric": metric,
            "label": METRIC_LABELS.get(metric, metric),
            "delta": delta,
            "improvement_magnitude": signed_improvement,
        }
        if signed_improvement > 0 and (
            largest_improvement is None
            or signed_improvement > largest_improvement["improvement_magnitude"]
        ):
            largest_improvement = rec
        if signed_improvement < 0 and (
            largest_regression is None
            or signed_improvement < largest_regression["improvement_magnitude"]
        ):
            largest_regression = rec

    trend_summary = _build_trend_summary(delta_map)

    today = date.today()
    sync_stale = (today - latest_overall).days > STALE_AFTER_DAYS

    return {
        "latest_date": latest_overall,
        "previous_date": previous_date,
        "days_between": days_between,
        "latest": latest_map,
        "previous": previous_map,
        "units": units_map,
        "delta": delta_map,
        "delta_pct": delta_pct_map,
        "metric_labels": {m: METRIC_LABELS.get(m, m) for m in latest_map},
        "largest_improvement": largest_improvement,
        "largest_regression": largest_regression,
        "trend_summary": trend_summary,
        "sync_stale": sync_stale,
        "total_metrics_tracked": len(latest_map),
    }


def render_comparison_message(snapshot: dict | None) -> str:
    """Render a deterministic, grounded "compare to last time" message.

    Pure function over the snapshot dict — no DB access, no clock reads.
    Beth's body-composition handler calls this for the comparative answer.
    PR / weight-loss judgments are never introduced; we report what the
    user measured. PRs are NEVER the framing.
    """
    if snapshot is None:
        return (
            "You haven't logged any body measurements in WLJ yet. "
            "Once you log them under Health → Body Composition, "
            "I'll be able to compare each entry to your previous one."
        )

    latest_date = snapshot["latest_date"]
    previous_date = snapshot.get("previous_date")
    deltas = snapshot.get("delta") or {}
    units = snapshot.get("units") or {}
    labels = snapshot.get("metric_labels") or {}
    latest_map = snapshot.get("latest") or {}

    compared = [(m, d) for m, d in deltas.items() if d is not None]
    no_history = [m for m, d in deltas.items() if d is None]

    if not compared:
        # User has logged measurements but no prior session for any of
        # them — honest, specific answer (no "I don't have access").
        listing = ", ".join(
            f"{labels.get(m, m)} {latest_map.get(m, 0):g}{units.get(m, '')}"
            for m in latest_map
        )
        return (
            f"You logged measurements on "
            f"{latest_date.strftime('%b %d, %Y')}: {listing}. "
            f"This is the first session in WLJ for these metrics, so "
            f"there's no previous entry to compare against yet."
        )

    compared.sort(key=lambda kv: labels.get(kv[0], kv[0]).lower())
    lines = []
    for metric, delta in compared:
        unit = units.get(metric, "")
        label = labels.get(metric, metric)
        sign = "+" if delta > 0 else ""
        lines.append(f"{label}: {sign}{delta:g}{unit}")

    when_phrase = (
        f"Compared to your previous measurement on "
        f"{previous_date.strftime('%b %d, %Y')}"
        if previous_date
        else "Compared to your previous measurement"
    )
    parts = [
        f"You logged new body measurements on "
        f"{latest_date.strftime('%b %d, %Y')}.\n\n{when_phrase}:\n"
        + "\n".join(lines)
    ]

    biggest = snapshot.get("largest_improvement")
    if biggest is not None:
        d = biggest["delta"]
        unit = units.get(biggest["metric"], "")
        sign = "+" if d > 0 else ""
        parts.append(
            f"\nBiggest win: {biggest['label']} moved "
            f"{sign}{d:g}{unit} — a meaningful step in the right "
            f"direction."
        )

    if no_history:
        no_hist_names = ", ".join(labels.get(m, m) for m in no_history[:4])
        parts.append(
            f"\nFirst entry (no prior comparison yet): {no_hist_names}."
        )

    return "\n".join(parts)


def render_latest_message(snapshot: dict | None) -> str:
    """Render a deterministic "what are my latest measurements?" answer."""
    if snapshot is None:
        return (
            "You haven't logged any body measurements in WLJ yet."
        )
    latest_date = snapshot["latest_date"]
    latest_map = snapshot.get("latest") or {}
    units = snapshot.get("units") or {}
    labels = snapshot.get("metric_labels") or {}
    rows = sorted(
        latest_map.keys(), key=lambda m: labels.get(m, m).lower(),
    )
    listing = "\n".join(
        f"{labels.get(m, m)}: {latest_map[m]:g}{units.get(m, '')}"
        for m in rows
    )
    return (
        f"Your latest body measurements (logged "
        f"{latest_date.strftime('%b %d, %Y')}):\n{listing}"
    )


# ── Internals ───────────────────────────────────────────────────────────


def _build_trend_summary(deltas: dict) -> list[str]:
    """Per-metric one-line verdicts using TREND_NOISE_THRESHOLD.

    A metric appears only when a delta is reported. Stable metrics get
    an explicit "Stable" line so the user can see they were considered.
    "improving" tag is only added when the direction-of-improvement
    matches; otherwise we report direction only.
    """
    summary = []
    ordered = sorted(
        deltas.keys(),
        key=lambda m: METRIC_LABELS.get(m, m).lower(),
    )
    for metric in ordered:
        delta = deltas.get(metric)
        if delta is None:
            continue
        threshold = TREND_NOISE_THRESHOLD.get(metric, 0.25)
        label = METRIC_LABELS.get(metric, metric)
        if abs(delta) < threshold:
            summary.append(f"{label} stable")
            continue
        direction_label = "down" if delta < 0 else "up"
        improvement_dir = METRIC_IMPROVEMENT_DIRECTION.get(metric, "none")
        if improvement_dir == "none":
            summary.append(f"{label} trending {direction_label}")
        elif improvement_dir == direction_label:
            summary.append(f"{label} trending {direction_label} (improving)")
        else:
            summary.append(f"{label} trending {direction_label}")
    return summary
