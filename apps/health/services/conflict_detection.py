"""
Physical Intelligence V2 — Conflict Detection.

Path: apps/health/services/conflict_detection.py
Purpose: Detect contradictions between user inputs (nutrition, training)
         and physical outcomes (body composition, performance).

Architecture:
    - Pure function: all data passed in, no DB queries inside detectors
    - Returns max 2 conflicts, severity-sorted
    - Conflicts are informational — they enrich narratives and can
      correct false-negative outcome validation (e.g., creatine masking)
    - Called by compute_physical_decision(), never on request path

Copyright: (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def detect_conflicts(user, signals, body_comp_trend, outcome):
    """Run all conflict detectors. Return max 2 conflicts, most severe first.

    Args:
        user: Django User instance
        signals: dict with keys like 'nutrition_score', 'training_score',
                 'recovery_score', 'hydration_score'
        body_comp_trend: dict from compute_body_composition_trend()
        outcome: dict from validate_outcome()

    Returns:
        list of conflict dicts, max 2, sorted by severity.
        Each dict: {type, description, resolution, severity, positive}
    """
    try:
        return _detect(user, signals, body_comp_trend, outcome)
    except Exception:
        logger.error(
            "Conflict detection failed for user %s", user.pk, exc_info=True
        )
        return []


def _detect(user, signals, trend, outcome):
    """Core detection logic."""
    found = []
    nutrition_score = signals.get("nutrition_score", 0)
    training_score = signals.get("training_score", 0)
    recovery_score = signals.get("recovery_score")
    outcome_status = outcome.get("outcome_status", "unknown")

    # ── 1. Compliant But Stalled ──
    if (
        nutrition_score >= 80
        and training_score >= 80
        and outcome_status == "not_working"
        and trend.get("plateau_status") in ("confirmed", "possible")
    ):
        found.append({
            "type": "compliant_but_stalled",
            "description": (
                "High compliance across nutrition and training "
                "but no body composition change"
            ),
            "resolution": (
                "Deficit may need recalculating. TDEE decreases as weight drops — "
                "what worked 10 lbs ago may not create a deficit now. "
                "Consider a structured diet break (eat at maintenance for 1-2 weeks) "
                "to reset metabolic adaptation."
            ),
            "severity": "high",
            "positive": False,
        })

    # ── 2. Creatine Weight Gain Masking ──
    # Check both the signal flag (consistent usage) and recent start
    creatine_flag = signals.get("creatine_active", False)
    if (
        (creatine_flag or _started_creatine_recently(user, days=21))
        and trend.get("fat_loss_status") in ("not_confirmed", "reversed")
        and _waist_not_gaining(trend)
    ):
        found.append({
            "type": "creatine_weight_gain",
            "description": (
                "Weight up but waist stable — likely creatine water retention, "
                "not fat gain"
            ),
            "resolution": (
                "Creatine causes 2-5 lbs of water retention in the first 2-3 weeks. "
                "Waist measurement is stable, confirming fat is not increasing. "
                "Ignore scale weight for 3-4 weeks after starting creatine. "
                "Trust tape measurements."
            ),
            "severity": "medium",
            "positive": True,
        })

    # ── 3. Overtraining Paradox ──
    if (
        training_score >= 90
        and recovery_score is not None
        and recovery_score < 40
        and trend.get("muscle_gain_status") in ("unlikely", "unclear")
    ):
        found.append({
            "type": "overtraining",
            "description": (
                "Very high training volume with declining recovery and results"
            ),
            "resolution": (
                "More training is producing worse results. Cortisol from overtraining "
                "promotes fat retention and muscle breakdown. A deload week at 50% "
                "volume would likely improve both recovery and body composition "
                "within 2 weeks."
            ),
            "severity": "critical",
            "positive": False,
        })

    # ── 4. Scale Flat But Recomposing (Positive) ──
    if trend.get("recomposition_status") or trend.get("verdict") == "recomposition":
        found.append({
            "type": "recomp_hidden",
            "description": (
                "Scale flat but fat decreasing and muscle increasing"
            ),
            "resolution": (
                "One of the best outcomes possible. Fat and muscle are changing "
                "at similar rates, so the scale doesn't move. Trust measurements "
                "and strength numbers. This is working."
            ),
            "severity": "low",
            "positive": True,
        })

    # ── 5. Sleep Undermining Everything ──
    sleep_hours = signals.get("sleep_hours")
    if (
        sleep_hours is not None
        and sleep_hours < 6
        and recovery_score is not None
        and recovery_score < 50
        and nutrition_score >= 70
        and training_score >= 70
    ):
        found.append({
            "type": "sleep_sabotage",
            "description": (
                "Good nutrition and training but sleep deprivation "
                "undermining recovery"
            ),
            "resolution": (
                "With less than 6 hours of sleep, growth hormone drops ~70% "
                "and cortisol rises significantly. No amount of perfect nutrition "
                "or training compensates. One extra hour of sleep would do more "
                "for progress than any other single change."
            ),
            "severity": "high",
            "positive": False,
        })

    # Sort by severity priority, return max 2
    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    found.sort(key=lambda c: SEVERITY_ORDER.get(c["severity"], 9))
    return found[:2]


def apply_conflict_corrections(outcome, conflicts):
    """Allow positive conflicts to correct false-negative outcome validation.

    For example: creatine weight gain makes outcome look like 'not_working'
    when the cut IS actually working (waist is down).

    Args:
        outcome: dict from validate_outcome() (will be mutated)
        conflicts: list from detect_conflicts()

    Returns:
        outcome dict (same reference, possibly mutated)
    """
    for c in conflicts:
        if not c.get("positive"):
            continue

        if (
            c["type"] == "creatine_weight_gain"
            and outcome.get("outcome_status") in ("not_working", "unknown")
        ):
            outcome["outcome_status"] = "working"
            outcome["outcome_evidence"] = outcome.get("outcome_evidence", []) + [
                "creatine_masking_scale"
            ]

        if (
            c["type"] == "recomp_hidden"
            and outcome.get("outcome_status") in ("not_working", "unknown")
        ):
            outcome["outcome_status"] = "working"
            outcome["outcome_evidence"] = outcome.get("outcome_evidence", []) + [
                "recomposition_detected"
            ]

    return outcome


# =========================================================================
# Helpers
# =========================================================================


def _started_creatine_recently(user, days=21):
    """Check if user started creatine within the last N days.

    Uses WaterEntry drink_type='creatine' as the primary source.
    Falls back to MedicineLog for creatine-related entries.
    """
    try:
        from apps.health.models import WaterEntry

        start = WaterEntry.creatine_start_date(user)
        if start and (date.today() - start).days <= days:
            return True
    except Exception:
        pass

    # Fallback to MedicineLog for users who track creatine as medication
    try:
        from apps.health.models import MedicineLog

        cutoff = date.today() - timedelta(days=days)
        return MedicineLog.objects.filter(
            medicine__user=user,
            medicine__name__icontains="creatine",
            scheduled_date__gte=cutoff,
        ).exists()
    except Exception:
        return False


def _waist_not_gaining(trend):
    """Check that waist is not increasing."""
    waist_trend = trend.get("waist_trend", 0)
    waist_evidence = trend.get("fat_loss_evidence", [])
    return waist_trend <= 0.1 and "waist_up" not in waist_evidence
