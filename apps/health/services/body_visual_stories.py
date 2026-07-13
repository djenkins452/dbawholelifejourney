# ==============================================================================
# File: apps/health/services/body_visual_stories.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic FACTS for the Executive Visual Story — Body Shape and
#              Limb Development. Facts only: current values, honest change, freshness,
#              significance, and missing-data reasons. No mission color, no verdict.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-13
# ==============================================================================
"""Executive Visual Story — the FACT layer for Body Shape and Limb Development (II-A).

These two visuals answer, in about five seconds and without reading the table:
  * **Body Shape** — "How is my shape changing?" (which regions expanded, contracted,
    held stable, or lack data — between the latest check-in and the previous one).
  * **Limb Development** — "How are my limbs changing, and are my left and right sides
    balanced?"

This module produces ONLY deterministic facts, arranged for those visuals. It is
deliberately **not** the future shared ``region_state`` primitive (that is design-only
for now — see ``docs/WLJ_BODY_REGION_STATE_DESIGN.md``). It does not decide mission
alignment, does not emit green/yellow/red, and never narrates a cause. WLJ owns the
truth and the calculation; the template owns neutral presentation; the conversational
model owns interpretation.

Honesty contract (the Visual Truth states every region can be in):
  * ``changed``       — a comparison exists AND the delta clears the measurement-noise
                        threshold. Carries a direction (``up`` / ``down``) and magnitude.
  * ``stable``        — a comparison exists but the delta is within measurement noise.
  * ``current_only``  — only one reading; current value is known, change is NOT.
  * ``missing``       — the region has never been measured (rendered honestly, never faked).
Orthogonal flags: ``stale`` (the latest reading is old) and ``low_confidence`` (a change
resting on a stale or very wide comparison). "We know this changed" must never look like
"we only know the current value."

Request-path-safe: pure arrangement of the pre-computed body-composition snapshot.
"""
from __future__ import annotations

import logging
from datetime import date

from apps.health.services.body_composition_snapshot import (
    METRIC_LABELS,
    STALE_AFTER_DAYS,
    TREND_NOISE_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Torso regions for Body Shape, top→bottom (the silhouette order). Illustrative only —
# the figure is NOT scaled to circumference (circumference ≠ visible width); it locates
# WHERE change happened, not an anatomically exact body.
BODY_SHAPE_REGIONS = ["neck", "shoulders", "chest", "waist", "hips"]

# Limb pairs for Limb Development (left/right metric names).
LIMB_PAIRS = [
    ("arm", "Upper arm", "arm_left", "arm_right"),
    ("forearm", "Forearm", "forearm_left", "forearm_right"),
    ("thigh", "Thigh", "thigh_left", "thigh_right"),
    ("calf", "Calf", "calf_left", "calf_right"),
]

# A comparison older than this (days between the two readings) makes a change
# "low confidence" — too much can happen across a wide gap for the delta to be crisp.
WIDE_COMPARISON_DAYS = 120


def _iso(d):
    return d.isoformat() if isinstance(d, date) else None


def region_fact(snapshot: dict, metric: str) -> dict:
    """Honest facts for one measured region. Facts + state + flags only — no verdict,
    no mission direction, no color. Safe against missing keys."""
    label = METRIC_LABELS.get(metric, metric)
    latest = (snapshot.get("latest") or {}).get(metric)
    if latest is None:
        return {"metric": metric, "label": label, "state": "missing",
                "current": None, "unit": (snapshot.get("units") or {}).get(metric, "in")}

    prev = (snapshot.get("previous") or {}).get(metric)
    delta = (snapshot.get("delta") or {}).get(metric)
    delta_pct = (snapshot.get("delta_pct") or {}).get(metric)
    unit = (snapshot.get("units") or {}).get(metric, "in")
    ldate = (snapshot.get("latest_date_per_metric") or {}).get(metric)
    pdate = (snapshot.get("previous_date_per_metric") or {}).get(metric)
    threshold = TREND_NOISE_THRESHOLD.get(metric, 0.25)

    today = date.today()
    stale = bool(ldate and (today - ldate).days > STALE_AFTER_DAYS)

    fact = {
        "metric": metric, "label": label, "current": round(latest, 2), "unit": unit,
        "comparison": None if prev is None else round(prev, 2),
        "delta": delta, "delta_pct": delta_pct,
        "latest_date": _iso(ldate), "previous_date": _iso(pdate),
        "days_between": (ldate - pdate).days if (ldate and pdate) else None,
        "threshold": threshold, "stale": stale, "low_confidence": False,
        "direction": None, "magnitude": None,
    }

    if prev is None or delta is None:
        fact["state"] = "current_only"
        return fact

    significant = abs(delta) >= threshold
    if not significant:
        fact["state"] = "stable"
        return fact

    fact["state"] = "changed"
    fact["direction"] = "up" if delta > 0 else "down"
    fact["magnitude"] = abs(round(delta, 2))
    wide = fact["days_between"] is not None and fact["days_between"] > WIDE_COMPARISON_DAYS
    fact["low_confidence"] = bool(stale or wide)
    return fact


def _counts(facts) -> dict:
    c = {"changed": 0, "stable": 0, "current_only": 0, "missing": 0}
    for f in facts:
        c[f["state"]] = c.get(f["state"], 0) + 1
    return c


def build_body_shape(snapshot: dict | None) -> dict:
    """Body Shape facts — one entry per torso region, in silhouette order.

    Returns ``{regions, comparison_window, counts, largest_change, has_comparison,
    has_any}``. Empty-safe.
    """
    if not snapshot:
        return {"regions": [], "comparison_window": None,
                "counts": {"changed": 0, "stable": 0, "current_only": 0, "missing": 5},
                "largest_change": None, "has_comparison": False, "has_any": False}

    regions = [region_fact(snapshot, m) for m in BODY_SHAPE_REGIONS]
    counts = _counts(regions)
    has_comparison = counts["changed"] + counts["stable"] > 0
    window = None
    if snapshot.get("latest_date") and snapshot.get("previous_date"):
        window = {"latest_date": _iso(snapshot["latest_date"]),
                  "previous_date": _iso(snapshot["previous_date"]),
                  "days_between": snapshot.get("days_between")}

    # Largest CHANGE — the region that moved most by absolute delta. Factual only:
    # magnitude + direction, NOT a verdict about whether the change is "good" (that
    # needs a reviewed target-direction contract, deferred). None when nothing changed.
    changed = [r for r in regions if r["state"] == "changed"]
    largest_change = None
    if changed:
        top = max(changed, key=lambda r: r["magnitude"] or 0)
        largest_change = {"metric": top["metric"], "label": top["label"],
                          "delta": top["delta"], "magnitude": top["magnitude"],
                          "direction": top["direction"], "unit": top["unit"]}

    return {"regions": regions, "comparison_window": window, "counts": counts,
            "largest_change": largest_change, "has_comparison": has_comparison,
            "has_any": counts["missing"] < len(BODY_SHAPE_REGIONS)}


def build_limb_development(snapshot: dict | None) -> dict:
    """Limb Development facts — one entry per limb pair with left, right, and honest
    left/right balance. Balance and change are facts; no muscle-preservation claim.

    Returns ``{limbs, has_comparison, has_any}``. Empty-safe.
    """
    empty = {"limbs": [], "has_comparison": False, "has_any": False}
    if not snapshot:
        return empty

    limbs = []
    any_measured = False
    any_comparison = False
    for key, label, lm, rm in LIMB_PAIRS:
        left = region_fact(snapshot, lm)
        right = region_fact(snapshot, rm)
        measured = left["state"] != "missing" or right["state"] != "missing"
        any_measured = any_measured or measured
        if left["state"] in ("changed", "stable") or right["state"] in ("changed", "stable"):
            any_comparison = True

        asymmetry = None
        if left.get("current") is not None and right.get("current") is not None:
            diff = round(abs(left["current"] - right["current"]), 2)
            thr = TREND_NOISE_THRESHOLD.get(lm, 0.25)
            larger = None
            if left["current"] > right["current"]:
                larger = "left"
            elif right["current"] > left["current"]:
                larger = "right"
            # Left/right measured on different days? Then the gap is partly timing.
            diff_dates = bool(left.get("latest_date") and right.get("latest_date")
                              and left["latest_date"] != right["latest_date"])
            asymmetry = {"diff": diff, "larger": larger,
                         "significant": diff >= thr and larger is not None,
                         "threshold": thr, "different_dates": diff_dates}

        limbs.append({"key": key, "label": label, "left": left, "right": right,
                      "asymmetry": asymmetry, "measured": measured})

    return {"limbs": limbs, "has_comparison": any_comparison, "has_any": any_measured}
