# ==============================================================================
# File: apps/health/services/health_concept_view.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Concept-organized DETERMINISTIC health facts for the executive-assessment
#   evidence package — the facts a health expert perceives grouped as concepts (body
#   composition, cardiovascular, glucose, sleep & recovery, activity, hydration,
#   respiratory), with WLJ's own reasoning (scores, verdicts, status labels, narratives,
#   advice) DELIBERATELY EXCLUDED. WLJ organizes; the model prioritizes, interprets, and
#   advises.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Health concept view — deterministic facts, organized the way an expert perceives them.

WHY THIS EXISTS (the boundary, held strictly): the health SAE snapshot the model was being
handed is 115 co-equal keys that MIX raw facts with WLJ's finished reasoning — a per-category
scorecard (`health_score_drivers`), a written narrative + recommendation (`physical_decision`),
a named verdict (`fat_loss_phase: "RECOMPOSITION"`), status judgments (`*_status`), ranked
"largest_improvement", "improving" annotations. Handed a scorecard and a pre-written report,
the model produces a report. Those are exactly the things that must stay the MODEL's: what
matters, what it means, the story, the advice.

This builder does ONLY two things, both deterministic:
  1. SELECTS the raw facts (values + the change WLJ already measured) — never a score, status
     label, verdict, narrative, rank, or recommendation.
  2. GROUPS them into the concepts a health expert naturally thinks in (a fixed ontology —
     design-time schema, not a per-user judgment), so related facts (weight + fat mass +
     lean mass) arrive as ONE object and their relationship is perceptible.

It computes nothing new and decides nothing. Prioritization, significance, causality,
synthesis, and advice remain entirely the model's.
"""

import logging

logger = logging.getLogger(__name__)


def _num(v):
    """Pass through a plain number, else None. Never coerce a label/verdict into a fact."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _member(label, value, unit=None, change=None):
    m = {"label": label, "value": value}
    if unit:
        m["unit"] = unit
    if change is not None:
        m["change"] = change
    return m


def build_health_concept_view(state):
    """Return {concepts: {<concept>: {label, members: {<metric>: {label, value, unit, change}}}}}
    built from the deterministic facts in the health SAE `state`. Facts only; reasoning
    excluded. Missing facts are simply omitted (never fabricated). Never raises."""
    if not isinstance(state, dict):
        return {"concepts": {}}
    try:
        return {"concepts": _compose(state)}
    except Exception:
        logger.warning("health_concept_view: compose failed", exc_info=True)
        return {"concepts": {}}


def _compose(s):
    bc = s.get("body_composition") if isinstance(s.get("body_composition"), dict) else {}
    bc_latest = bc.get("latest") or {}
    bc_delta = bc.get("delta") or {}
    concepts = {}

    # -- Body composition: the components (weight = fat mass + lean mass) as ONE object, so
    #    the model can SEE the relationship. Facts only — no "improving", no verdict. --------
    body = {}
    if _num(s.get("weight_current")) is not None:
        body["weight"] = _member("Weight", s.get("weight_current"), "lb",
                                 _num(s.get("weight_change_30d")))
    if _num(bc_latest.get("fat_mass")) is not None:
        body["fat_mass"] = _member("Fat mass", bc_latest.get("fat_mass"), "lb",
                                  _num(bc_delta.get("fat_mass")))
    if _num(bc_latest.get("lean_mass")) is not None:
        body["lean_mass"] = _member("Lean mass", bc_latest.get("lean_mass"), "lb",
                                   _num(bc_delta.get("lean_mass")))
    if _num(s.get("body_fat_current")) is not None:
        body["body_fat_pct"] = _member("Body fat", s.get("body_fat_current"), "%",
                                       _num(bc_delta.get("body_fat_pct")))
    if _num(s.get("waist_current")) is not None:
        body["waist"] = _member("Waist", s.get("waist_current"), "in",
                               _num(bc_delta.get("waist")))
    if _num(s.get("bmi_current")) is not None:
        body["bmi"] = _member("BMI", s.get("bmi_current"), None, _num(bc_delta.get("bmi")))
    if body:
        concepts["body_composition"] = {
            "label": "Body composition",
            # A neutral factual identity (arithmetic, not a verdict) so the relationship is
            # explicit: the model still decides what it MEANS.
            "relationship": "weight change ≈ fat-mass change + lean-mass change",
            "members": body,
            "change_basis": {"from": bc.get("previous_date"), "to": bc.get("latest_date")},
        }

    # -- Glucose / metabolic ----------------------------------------------------------------
    gs = s.get("glucose_summary") if isinstance(s.get("glucose_summary"), dict) else {}
    glucose = {}
    for key, label, src in (("avg_7d", "Avg (7d)", s.get("glucose_avg_7d")),
                            ("avg_30d", "Avg (30d)", s.get("glucose_avg_30d")),
                            ("avg_90d", "Avg (90d)", s.get("glucose_avg_90d")),
                            ("latest", "Latest", s.get("latest_glucose")),
                            ("time_in_range_7d", "Time in range (7d)",
                             s.get("time_in_range_pct_7d")),
                            ("time_in_range_30d", "Time in range (30d)",
                             s.get("time_in_range_pct_30d")),
                            ("variability", "Variability", s.get("glucose_variability")),
                            ("projected_a1c", "Projected A1C", s.get("projected_a1c"))):
        if _num(src) is not None:
            unit = "%" if "range" in key else ("mg/dL" if "avg" in key or key == "latest" else None)
            glucose[key] = _member(label, src, unit)
    if glucose:
        concepts["glucose"] = {"label": "Glucose / metabolic", "members": glucose}

    # -- Cardiovascular ---------------------------------------------------------------------
    cardio = {}
    if s.get("bp_reading"):
        cardio["blood_pressure"] = _member("Blood pressure", s.get("bp_reading"), "mmHg")
    if _num(s.get("heart_rate_avg_7d")) is not None:
        cardio["resting_heart_rate"] = _member("Heart rate (7d avg)",
                                              s.get("heart_rate_avg_7d"), "bpm")
    if cardio:
        concepts["cardiovascular"] = {"label": "Cardiovascular", "members": cardio}

    # -- Sleep & recovery -------------------------------------------------------------------
    recovery = {}
    if _num(s.get("sleep_avg_hours_7d")) is not None:
        recovery["sleep_avg_hours_7d"] = _member("Sleep (7d avg)",
                                                s.get("sleep_avg_hours_7d"), "h")
    if _num(s.get("sleep_last_night_hours")) is not None:
        recovery["sleep_last_night"] = _member("Sleep last night",
                                             s.get("sleep_last_night_hours"), "h")
    if _num(s.get("sleep_good_nights_7d")) is not None:
        recovery["good_nights_7d"] = _member("Nights ≥7h (of 7)", s.get("sleep_good_nights_7d"))
    if _num(s.get("latest_hrv")) is not None:
        recovery["hrv"] = _member("HRV", s.get("latest_hrv"), "ms")
    if recovery:
        concepts["sleep_recovery"] = {"label": "Sleep & recovery", "members": recovery}

    # -- Activity ---------------------------------------------------------------------------
    activity = {}
    if _num(s.get("steps_avg_7d")) is not None:
        activity["steps_avg_7d"] = _member("Steps (7d avg)", s.get("steps_avg_7d"))
    if activity:
        concepts["activity"] = {"label": "Activity", "members": activity}

    # -- Hydration --------------------------------------------------------------------------
    hydration = {}
    if _num(s.get("water_avg_oz_7d")) is not None:
        hydration["avg_oz_7d"] = _member("Water (7d avg)", s.get("water_avg_oz_7d"), "oz")
    if _num(s.get("water_goal_oz")) is not None:
        hydration["goal_oz"] = _member("Daily goal", s.get("water_goal_oz"), "oz")
    if hydration:
        concepts["hydration"] = {"label": "Hydration", "members": hydration}

    # -- Respiratory ------------------------------------------------------------------------
    resp = {}
    if _num(s.get("blood_oxygen_avg_7d")) is not None:
        resp["spo2_avg_7d"] = _member("Blood oxygen (7d avg)", s.get("blood_oxygen_avg_7d"), "%")
    if _num(s.get("latest_respiratory_rate")) is not None:
        resp["respiratory_rate"] = _member("Respiratory rate",
                                          s.get("latest_respiratory_rate"), "br/min")
    if resp:
        concepts["respiratory"] = {"label": "Respiratory", "members": resp}

    return concepts
