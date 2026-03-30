"""
Physical Intelligence V2 — Body Composition Signal.

Path: apps/health/services/body_composition_signal.py
Purpose: Synthesize body composition trend from weight, waist, and
         DailyHealthSummary pre-computed data.

Architecture:
    - Pure function: reads pre-computed data, returns a dict
    - Called once per SAE cycle, result cached in SAE state
    - NEVER called on request path
    - Uses voting system: multiple evidence sources each cast a vote
    - Trend-based (14-28 day windows), never single-day values

Copyright: (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

logger = logging.getLogger(__name__)


def compute_body_composition_trend(user, as_of_date=None):
    """Synthesize body composition trend from existing pre-computed data.

    Data sources (all pre-computed, never live):
    - DailyHealthSummary: fat_loss_quality, recomp_flag, plateau_status,
      muscle_loss_risk, fat_loss_speed, muscle_preservation_status
    - BodyCompositionEntry: tape measurements (waist primarily)
    - WeightEntry: weight history

    Args:
        user: Django User instance
        as_of_date: Date to compute for (default: today)

    Returns:
        dict with fat_loss_status, muscle_gain_status, recomposition_status,
        weight_trend, waist_trend, confidence, velocity, plateau info.
    """
    if as_of_date is None:
        as_of_date = date.today()

    try:
        return _compute(user, as_of_date)
    except Exception:
        logger.error(
            "Body composition signal failed for user %s", user.pk, exc_info=True
        )
        return _insufficient_data()


def _compute(user, as_of_date):
    """Core computation. Separated for clean error handling."""
    from apps.health.models import BodyCompositionEntry, DailyHealthSummary, WeightEntry

    # ── Gather DailyHealthSummary data ──
    summaries = list(
        DailyHealthSummary.objects.filter(
            user=user,
            summary_date__gte=as_of_date - timedelta(days=28),
            summary_date__lte=as_of_date,
        )
        .order_by("-summary_date")
        .values(
            "summary_date",
            "weight",
            "baseline_ready",
            "fat_loss_quality_label",
            "fat_loss_speed_pct_per_week",
            "fat_loss_speed_label",
            "recomposition_flag_14d",
            "plateau_status",
            "plateau_risk_score",
            "plateau_risk_label",
            "muscle_loss_risk_score",
            "muscle_loss_risk_level",
            "muscle_preservation_status",
            "fat_loss_phase",
            "recovery_score",
        )
    )

    today_summary = summaries[0] if summaries else None

    if not today_summary or not today_summary.get("baseline_ready"):
        return _insufficient_data()

    # ── Assess fat loss ──
    fat_loss_status, fat_loss_evidence = _assess_fat_loss(
        today_summary, summaries, user, as_of_date
    )

    # ── Assess muscle ──
    muscle_gain_status, muscle_evidence = _assess_muscle(
        today_summary, summaries, user, as_of_date
    )

    # ── Compute velocity ──
    weight_trend = _compute_weight_trend(summaries)
    waist_trend = _compute_waist_trend(user, as_of_date)
    velocity = _compute_velocity(today_summary, user, as_of_date)

    # ── Detect plateau ──
    plateau_info = _detect_plateau(today_summary, summaries, velocity)

    # ── Composite verdict ──
    recomposition_status = (
        fat_loss_status in ("confirmed", "likely")
        and muscle_gain_status in ("likely",)
    ) or bool(today_summary.get("recomposition_flag_14d"))

    # ── Confidence ──
    confidence = _compute_confidence(user, as_of_date, summaries)

    return {
        "fat_loss_status": fat_loss_status,
        "fat_loss_evidence": fat_loss_evidence,
        "muscle_gain_status": muscle_gain_status,
        "muscle_evidence": muscle_evidence,
        "recomposition_status": recomposition_status,
        "weight_trend": weight_trend,
        "waist_trend": waist_trend,
        "confidence": confidence,
        # Velocity
        "fat_loss_rate_lbs_per_week": velocity.get("weight_rate"),
        "fat_loss_speed": velocity.get("speed_label"),
        "waist_rate_per_week": velocity.get("waist_rate"),
        # Plateau
        "plateau_status": plateau_info["status"],
        "plateau_type": plateau_info["type"],
        "plateau_days": plateau_info["days"],
        # Composite verdict (for outcome validation)
        "verdict": _derive_verdict(fat_loss_status, muscle_gain_status),
    }


# =========================================================================
# Fat Loss Assessment (Voting System)
# =========================================================================


def _assess_fat_loss(today, summaries, user, as_of_date):
    """Multi-source voting for fat loss status.

    Each source votes: losing (+1), not losing (-1), or abstains (0).
    """
    votes = 0
    evidence = []

    # ── Source 1: DHS fat_loss_quality ──
    fql = today.get("fat_loss_quality_label")
    if fql in ("EXCELLENT", "GOOD"):
        votes += 1
        evidence.append("dhs_fat_loss_good")
    elif fql == "MUSCLE_LOSS_RISK":
        votes += 1  # Still losing fat, also losing muscle
        evidence.append("dhs_fat_loss_with_muscle_risk")
    elif fql == "MIXED":
        evidence.append("dhs_fat_loss_mixed")
    # INSUFFICIENT_DATA → abstain

    # ── Source 2: Weight trend (split-half comparison) ──
    weights = [float(s["weight"]) for s in summaries if s.get("weight")]
    if len(weights) >= 6:
        mid = len(weights) // 2
        first_half = sum(weights[:mid]) / mid
        second_half = sum(weights[mid:]) / (len(weights) - mid)
        delta = second_half - first_half

        if delta < -0.5:
            votes += 1
            evidence.append("weight_down")
        elif delta > 0.5:
            votes -= 1
            evidence.append("weight_up")
        else:
            evidence.append("weight_flat")

    # ── Source 3: Waist trend ──
    waist_delta, waist_ok = _measurement_trend(user, "waist", as_of_date, days=28)
    if waist_ok:
        if waist_delta < -0.25:
            votes += 1
            evidence.append("waist_down")
        elif waist_delta > 0.25:
            votes -= 1
            evidence.append("waist_up")
        else:
            evidence.append("waist_flat")

    # ── Source 4: Plateau flag ──
    plateau = today.get("plateau_status")
    if plateau == "TRUE_PLATEAU":
        votes -= 1
        evidence.append("plateau_detected")
    elif plateau == "RECOMP":
        evidence.append("recomp_not_stall")

    # ── Vote ──
    active_sources = sum(
        1
        for e in evidence
        if not e.endswith("_flat")
        and not e.endswith("_mixed")
        and e != "recomp_not_stall"
    )

    if active_sources == 0:
        return "not_confirmed", evidence

    ratio = votes / active_sources

    if ratio >= 0.6:
        return "confirmed", evidence
    elif ratio > 0:
        return "likely", evidence
    elif ratio > -0.6:
        return "not_confirmed", evidence
    else:
        return "reversed", evidence


# =========================================================================
# Muscle Assessment (Voting System)
# =========================================================================


def _assess_muscle(today, summaries, user, as_of_date):
    """Multi-source voting for muscle status."""
    votes = 0
    evidence = []

    # ── Source 1: Muscle preservation status ──
    mps = today.get("muscle_preservation_status")
    if mps == "HIGH_QUALITY":
        votes += 1
        evidence.append("preservation_high")
    elif mps == "MUSCLE_RISK":
        votes -= 1
        evidence.append("preservation_risk")
    elif mps == "MODERATE_QUALITY":
        evidence.append("preservation_moderate")

    # ── Source 2: Muscle loss risk score ──
    mlr = today.get("muscle_loss_risk_score")
    if mlr is not None:
        if mlr < 30:
            votes += 1
            evidence.append("low_risk_score")
        elif mlr > 70:
            votes -= 1
            evidence.append("high_risk_score")

    # ── Source 3: Recomposition flag ──
    if today.get("recomposition_flag_14d"):
        votes += 1
        evidence.append("recomp_flag")

    # ── Source 4: Muscle-region measurements ──
    muscle_metrics = ["chest", "arm_right", "thigh_right"]
    m_up, m_down = 0, 0
    for metric in muscle_metrics:
        delta, ok = _measurement_trend(user, metric, as_of_date, days=28)
        if ok:
            if delta > 0.15:
                m_up += 1
                evidence.append(f"{metric}_up")
            elif delta < -0.25:
                m_down += 1
                evidence.append(f"{metric}_down")

    if m_up >= 2:
        votes += 1
        evidence.append("measurements_growing")
    elif m_down >= 2:
        votes -= 1
        evidence.append("measurements_shrinking")

    # ── Vote ──
    active = sum(
        1
        for e in evidence
        if not e.endswith("_moderate")
    )
    if active == 0:
        return "unclear", evidence

    ratio = votes / active

    if ratio >= 0.5:
        return "likely", evidence
    elif ratio > -0.5:
        return "unclear", evidence
    else:
        return "unlikely", evidence


# =========================================================================
# Velocity & Plateau
# =========================================================================


def _compute_weight_trend(summaries):
    """Simple weight slope over the window. Negative = losing."""
    weights = [float(s["weight"]) for s in summaries if s.get("weight")]
    if len(weights) < 4:
        return 0.0
    first_half = sum(weights[len(weights) // 2 :]) / (len(weights) - len(weights) // 2)
    second_half = sum(weights[: len(weights) // 2]) / (len(weights) // 2)
    return round(second_half - first_half, 2)


def _compute_waist_trend(user, as_of_date):
    """Waist delta over 28 days."""
    delta, ok = _measurement_trend(user, "waist", as_of_date, days=28)
    return round(delta, 2) if ok else 0.0


def _compute_velocity(today, user, as_of_date):
    """Compute fat loss rate from DHS + waist measurements."""
    result = {
        "weight_rate": None,
        "speed_label": None,
        "waist_rate": None,
    }

    speed_pct = today.get("fat_loss_speed_pct_per_week")
    speed_label = today.get("fat_loss_speed_label")
    weight = today.get("weight")

    if speed_pct is not None and weight:
        weekly_lbs = float(weight) * float(speed_pct) / 100
        if speed_label == "GAINING":
            result["weight_rate"] = abs(weekly_lbs)
        else:
            result["weight_rate"] = -abs(weekly_lbs)

    SPEED_MAP = {
        "SAFE": "optimal",
        "SLOW": "slow",
        "FAST": "aggressive",
        "TOO_FAST": "dangerous",
        "GAINING": None,
    }
    result["speed_label"] = SPEED_MAP.get(speed_label)

    # Waist velocity
    from apps.health.models import BodyCompositionEntry

    waist_entries = list(
        BodyCompositionEntry.objects.filter(
            user=user,
            metric_name="waist",
            measurement_date__gte=as_of_date - timedelta(days=28),
            measurement_date__lte=as_of_date,
        )
        .order_by("measurement_date")
        .values_list("measurement_date", "value")
    )

    if len(waist_entries) >= 2:
        first_date, first_val = waist_entries[0]
        last_date, last_val = waist_entries[-1]
        days_span = (last_date - first_date).days
        if days_span >= 7:
            total_delta = float(last_val) - float(first_val)
            result["waist_rate"] = round(total_delta / (days_span / 7), 3)

    return result


def _detect_plateau(today, summaries, velocity):
    """Detect and classify plateaus."""
    dhs_plateau = today.get("plateau_status")
    dhs_risk_label = today.get("plateau_risk_label")

    # Count days of weight flatness
    weights = [float(s["weight"]) for s in summaries if s.get("weight")]
    flat_days = 0
    if len(weights) >= 7:
        recent_avg = sum(weights[:7]) / 7
        for i in range(7, len(weights)):
            window = weights[i : i + 7]
            if window:
                older_avg = sum(window) / len(window)
                if abs(recent_avg - older_avg) < 0.5:
                    flat_days = i
                    break

    if dhs_plateau == "TRUE_PLATEAU" or (
        flat_days >= 21 and dhs_risk_label == "HIGH"
    ):
        return {"status": "confirmed", "type": "true_plateau", "days": flat_days}
    elif dhs_plateau == "RECOMP":
        return {"status": "none", "type": "recomp_masking", "days": 0}
    elif dhs_plateau == "WATER":
        return {"status": "possible", "type": "noise", "days": flat_days}
    elif flat_days >= 10 and dhs_risk_label in ("RISING", "HIGH"):
        return {"status": "possible", "type": "temporary_stall", "days": flat_days}
    else:
        return {"status": "none", "type": None, "days": 0}


# =========================================================================
# Shared Utilities
# =========================================================================


def _measurement_trend(user, metric_name, as_of_date, days=28):
    """Get trend for a body measurement. Noise-smoothed with median filter.

    Returns: (delta_inches: float, is_reliable: bool)
    Reliable requires >= 2 data points after outlier filtering.
    """
    from apps.health.models import BodyCompositionEntry

    entries = list(
        BodyCompositionEntry.objects.filter(
            user=user,
            metric_name=metric_name,
            measurement_date__gte=as_of_date - timedelta(days=days),
            measurement_date__lte=as_of_date,
        )
        .order_by("measurement_date")
        .values_list("value", flat=True)
    )

    if len(entries) < 2:
        return 0.0, False

    float_entries = [float(v) for v in entries]

    # Median filter: reject outliers if 3+ entries
    if len(float_entries) >= 3:
        med = median(float_entries)
        # Allow 1.5 inches variance from median as tolerance
        float_entries = [v for v in float_entries if abs(v - med) <= 1.5]

    if len(float_entries) < 2:
        return 0.0, False

    delta = float_entries[-1] - float_entries[0]
    return delta, True


def _compute_confidence(user, as_of_date, summaries):
    """Confidence based on data source availability."""
    from apps.health.models import BodyCompositionEntry

    sources_found = 0
    total_sources = 4  # weight, waist, body_fat, measurements

    # Weight data (need at least 7 days)
    weight_days = sum(1 for s in summaries if s.get("weight"))
    if weight_days >= 7:
        sources_found += 1

    # Waist data
    waist_count = BodyCompositionEntry.objects.filter(
        user=user,
        metric_name="waist",
        measurement_date__gte=as_of_date - timedelta(days=28),
    ).count()
    if waist_count >= 2:
        sources_found += 1

    # Body fat data
    has_bf = any(s.get("fat_loss_quality_label") not in (None, "INSUFFICIENT_DATA") for s in summaries)
    if has_bf:
        sources_found += 1

    # Any muscle-region measurements
    muscle_count = BodyCompositionEntry.objects.filter(
        user=user,
        metric_name__in=["chest", "arm_right", "thigh_right"],
        measurement_date__gte=as_of_date - timedelta(days=28),
    ).count()
    if muscle_count >= 2:
        sources_found += 1

    if sources_found >= 3:
        return "high"
    elif sources_found >= 2:
        return "medium"
    else:
        return "low"


# =========================================================================
# Verdict Matrix
# =========================================================================

_VERDICT = {
    ("confirmed", "likely"): "recomposition",
    ("confirmed", "unclear"): "effective_cut",
    ("confirmed", "unlikely"): "cut_with_muscle_loss",
    ("likely", "likely"): "recomposition",
    ("likely", "unclear"): "effective_cut",
    ("likely", "unlikely"): "cut_with_muscle_loss",
    ("not_confirmed", "likely"): "effective_bulk",
    ("not_confirmed", "unclear"): "spinning_wheels",
    ("not_confirmed", "unlikely"): "regression",
    ("reversed", "likely"): "effective_bulk",
    ("reversed", "unclear"): "regression",
    ("reversed", "unlikely"): "regression",
}


def _derive_verdict(fat_loss, muscle):
    return _VERDICT.get((fat_loss, muscle), "no_data")


def _insufficient_data():
    """Return baseline insufficient data response."""
    return {
        "fat_loss_status": "not_confirmed",
        "fat_loss_evidence": [],
        "muscle_gain_status": "unclear",
        "muscle_evidence": [],
        "recomposition_status": False,
        "weight_trend": 0.0,
        "waist_trend": 0.0,
        "confidence": "low",
        "fat_loss_rate_lbs_per_week": None,
        "fat_loss_speed": None,
        "waist_rate_per_week": None,
        "plateau_status": "none",
        "plateau_type": None,
        "plateau_days": 0,
        "verdict": "no_data",
    }
