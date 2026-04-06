"""
Physical Intelligence V2 — Body Composition Signal.

Path: apps/health/services/body_composition_signal.py
Purpose: Synthesize body composition trend from weight, waist, and
         DailyHealthSummary pre-computed data.

Architecture:
    - Pure function: reads pre-computed data, returns a dict
    - Called once per SAE cycle, result cached in SAE state
    - NEVER called on request path
    - Uses WEIGHTED voting system: sources carry confidence
    - Includes data sufficiency gate, conflict resolution, creatine suppression
    - Trend-based (14-28 day windows), never single-day values

Copyright: (c) Whole Life Journey. All rights reserved.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

logger = logging.getLogger(__name__)

# =========================================================================
# Source confidence weights
# =========================================================================
# Body fat data quality tiers
CONFIDENCE_SCAN = 0.80        # DEXA, InBody, Bod Pod
CONFIDENCE_SCALE = 0.30       # Smart scale (noisy, ~5% error)
CONFIDENCE_MANUAL = 0.50      # Manual entry (reasonable but unverified)

# Weight trend confidence by data density
CONFIDENCE_WEIGHT_DENSE = 0.85   # 7+ points in window
CONFIDENCE_WEIGHT_SPARSE = 0.60  # 3-6 points

# Waist measurement confidence
CONFIDENCE_WAIST_GOOD = 0.80    # 3+ points with 14+ day span
CONFIDENCE_WAIST_MIN = 0.50     # 2 points

# Other sources
CONFIDENCE_PLATEAU = 0.70
CONFIDENCE_MUSCLE_PRESERVATION = 0.70
CONFIDENCE_MUSCLE_RISK_SCORE = 0.65
CONFIDENCE_RECOMP_FLAG = 0.75
CONFIDENCE_MUSCLE_TAPE = 0.60

# High-quality body fat scan sources (BodyCompositionEntry.source values)
HIGH_QUALITY_SOURCES = frozenset({"dexa_scan", "bod_pod", "inbody", "gym_scan"})
LOW_QUALITY_SOURCES = frozenset({"smart_scale", "apple_health"})

# Minimum data thresholds
MIN_WEIGHT_POINTS_7D = 3
MIN_WAIST_POINTS_14D = 2


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
        weight_trend, waist_trend, confidence, velocity, plateau info,
        plus fat_confidence, muscle_confidence, sufficiency, conflict_adjustments.
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

    # ── Data sufficiency ──
    sufficiency = _compute_sufficiency(user, as_of_date, summaries)

    # Hard gate: if both weight and waist are insufficient, bail
    if (
        sufficiency["weight_points_7d"] < MIN_WEIGHT_POINTS_7D
        and sufficiency["waist_points_14d"] < MIN_WAIST_POINTS_14D
    ):
        result = _insufficient_data()
        result["sufficiency"] = sufficiency
        return result

    # ── Assess fat loss (weighted voting) ──
    fat_loss_status, fat_loss_evidence, fat_confidence = _assess_fat_loss(
        today_summary, summaries, user, as_of_date, sufficiency
    )

    # ── Assess muscle (weighted voting) ──
    muscle_gain_status, muscle_evidence, muscle_confidence = _assess_muscle(
        today_summary, summaries, user, as_of_date, sufficiency
    )

    # ── Conflict resolution ──
    fat_loss_status, fat_confidence, conflict_adjustments = _resolve_conflicts(
        fat_loss_status,
        fat_confidence,
        fat_loss_evidence,
        sufficiency,
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

    # ── Confidence (overall) ──
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
        # Per-signal confidence (new)
        "fat_confidence": fat_confidence,
        "muscle_confidence": muscle_confidence,
        # Sufficiency & conflict resolution (new)
        "sufficiency": sufficiency,
        "conflict_adjustments": conflict_adjustments,
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
# Data Sufficiency
# =========================================================================


def _compute_sufficiency(user, as_of_date, summaries):
    """Count available data points to gate analysis quality.

    Returns a dict describing what data is available and at what quality level.
    This struct is passed to voting functions to set per-source confidence.
    """
    from apps.health.models import BodyCompositionEntry

    cutoff_7d = as_of_date - timedelta(days=7)
    cutoff_14d = as_of_date - timedelta(days=14)

    # Weight points from DHS summaries
    weight_points_7d = sum(
        1 for s in summaries
        if s.get("weight") and s["summary_date"] >= cutoff_7d
    )
    weight_points_28d = sum(1 for s in summaries if s.get("weight"))

    # Waist measurement points
    waist_qs = BodyCompositionEntry.objects.filter(
        user=user,
        metric_name="waist",
        measurement_date__lte=as_of_date,
    )
    waist_points_14d = waist_qs.filter(
        measurement_date__gte=cutoff_14d,
    ).count()
    waist_points_28d = waist_qs.filter(
        measurement_date__gte=as_of_date - timedelta(days=28),
    ).count()

    # Body fat data source quality
    # Check recent BodyCompositionEntry for body_fat_pct source
    recent_bf = (
        BodyCompositionEntry.objects.filter(
            user=user,
            metric_name="body_fat_pct",
            measurement_date__gte=as_of_date - timedelta(days=28),
            measurement_date__lte=as_of_date,
        )
        .order_by("-measurement_date")
        .values_list("source", flat=True)
        .first()
    )

    if recent_bf in HIGH_QUALITY_SOURCES:
        body_fat_source = "scan"
    elif recent_bf in LOW_QUALITY_SOURCES:
        body_fat_source = "scale"
    elif recent_bf:
        body_fat_source = "manual"
    else:
        body_fat_source = None

    # Creatine check (moved from conflict_detection for earlier suppression)
    creatine_within_21d = _check_creatine_recent(user, days=21)

    return {
        "weight_points_7d": weight_points_7d,
        "weight_points_28d": weight_points_28d,
        "waist_points_14d": waist_points_14d,
        "waist_points_28d": waist_points_28d,
        "body_fat_source": body_fat_source,
        "creatine_within_21d": creatine_within_21d,
    }


def _check_creatine_recent(user, days=21):
    """Check if user started creatine within the last N days."""
    try:
        from apps.health.models import Intake

        creatine = Intake.objects.filter(
            user=user,
            intake_type=Intake.INTAKE_TYPE_SUPPLEMENT,
            name__icontains="creatine",
            intake_status=Intake.STATUS_ACTIVE,
        ).first()
        if creatine and creatine.start_date:
            return (date.today() - creatine.start_date).days <= days
    except Exception:
        pass
    return False


# =========================================================================
# Fat Loss Assessment (Weighted Voting System)
# =========================================================================


def _assess_fat_loss(today, summaries, user, as_of_date, sufficiency):
    """Multi-source weighted voting for fat loss status.

    Each source votes with a confidence weight. The weighted sum determines
    the status, and the aggregate confidence is returned for downstream
    conflict resolution and UI gating.

    Returns: (status_str, evidence_list, confidence_float)
    """
    # Each vote: (direction, weight, label)
    # direction: +1 = losing fat, -1 = not losing / gaining
    weighted_votes = []
    evidence = []

    # ── Source 1: DHS fat_loss_quality ──
    fql = today.get("fat_loss_quality_label")
    # Confidence depends on data source quality
    dhs_conf = {
        "scan": CONFIDENCE_SCAN,
        "scale": CONFIDENCE_SCALE,
        "manual": CONFIDENCE_MANUAL,
    }.get(sufficiency["body_fat_source"], CONFIDENCE_SCALE)

    if fql in ("EXCELLENT", "GOOD"):
        weighted_votes.append((+1, dhs_conf, "dhs_fat_loss_good"))
        evidence.append("dhs_fat_loss_good")
    elif fql == "MUSCLE_LOSS_RISK":
        weighted_votes.append((+1, dhs_conf, "dhs_fat_loss_with_muscle_risk"))
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

        wt_conf = (
            CONFIDENCE_WEIGHT_DENSE
            if sufficiency["weight_points_7d"] >= 7
            else CONFIDENCE_WEIGHT_SPARSE
        )

        if delta < -0.5:
            weighted_votes.append((+1, wt_conf, "weight_down"))
            evidence.append("weight_down")
        elif delta > 0.5:
            weighted_votes.append((-1, wt_conf, "weight_up"))
            evidence.append("weight_up")
        else:
            evidence.append("weight_flat")

    # ── Source 3: Waist trend ──
    waist_delta, waist_ok = _measurement_trend(user, "waist", as_of_date, days=28)
    if waist_ok:
        waist_conf = (
            CONFIDENCE_WAIST_GOOD
            if sufficiency["waist_points_28d"] >= 3
            else CONFIDENCE_WAIST_MIN
        )
        if waist_delta < -0.25:
            weighted_votes.append((+1, waist_conf, "waist_down"))
            evidence.append("waist_down")
        elif waist_delta > 0.25:
            weighted_votes.append((-1, waist_conf, "waist_up"))
            evidence.append("waist_up")
        else:
            evidence.append("waist_flat")

    # ── Source 4: Plateau flag ──
    plateau = today.get("plateau_status")
    if plateau == "TRUE_PLATEAU":
        weighted_votes.append((-1, CONFIDENCE_PLATEAU, "plateau_detected"))
        evidence.append("plateau_detected")
    elif plateau == "RECOMP":
        evidence.append("recomp_not_stall")

    # ── Weighted vote tally ──
    if not weighted_votes:
        return "not_confirmed", evidence, 0.0

    weighted_sum = sum(d * w for d, w, _ in weighted_votes)
    total_weight = sum(w for _, w, _ in weighted_votes)
    ratio = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Confidence: average confidence of agreeing sources (same direction as result)
    result_direction = 1 if ratio > 0 else (-1 if ratio < 0 else 0)
    agreeing = [w for d, w, _ in weighted_votes if d == result_direction]
    fat_confidence = sum(agreeing) / len(agreeing) if agreeing else 0.0

    if ratio >= 0.5:
        return "confirmed", evidence, fat_confidence
    elif ratio > 0:
        return "likely", evidence, fat_confidence
    elif ratio > -0.5:
        return "not_confirmed", evidence, fat_confidence
    else:
        return "reversed", evidence, fat_confidence


# =========================================================================
# Conflict Resolution
# =========================================================================


def _resolve_conflicts(fat_loss_status, fat_confidence, evidence, sufficiency):
    """Apply deterministic conflict resolution rules.

    Rules prevent contradictory or unsupported conclusions.
    Returns: (resolved_status, resolved_confidence, adjustments_list)
    """
    adjustments = []

    # ── Rule 1: Weight down + waist not up → fat cannot be "reversed" ──
    weight_is_down = "weight_down" in evidence
    waist_is_up = "waist_up" in evidence
    if fat_loss_status == "reversed" and weight_is_down and not waist_is_up:
        fat_loss_status = "not_confirmed"
        fat_confidence = min(fat_confidence, 0.4)
        adjustments.append("rule1_weight_dominates")

    # ── Rule 2: No waist data → fat cannot be "reversed" ──
    if fat_loss_status == "reversed" and sufficiency["waist_points_14d"] < MIN_WAIST_POINTS_14D:
        fat_loss_status = "not_confirmed"
        fat_confidence = min(fat_confidence, 0.3)
        adjustments.append("rule2_waist_required_for_gain")

    # ── Rule 3: Insufficient active sources → downgrade confidence ──
    active_count = sum(
        1 for e in evidence
        if not e.endswith("_flat")
        and not e.endswith("_mixed")
        and e != "recomp_not_stall"
    )
    if active_count < 2:
        fat_confidence = min(fat_confidence, 0.35)
        if fat_loss_status in ("confirmed", "reversed"):
            fat_loss_status = "likely" if fat_loss_status == "confirmed" else "not_confirmed"
            adjustments.append("rule3_insufficient_active_sources")

    # ── Rule 4: Body fat scale cannot override weight+waist consensus ──
    # If scale-sourced DHS vote contradicts weight+waist consensus, drop it
    if sufficiency["body_fat_source"] == "scale":
        has_dhs_vote = any(
            e.startswith("dhs_fat_loss") and not e.endswith("_mixed")
            for e in evidence
        )
        if has_dhs_vote:
            # Check if weight+waist agree on a direction
            weight_direction = (
                1 if "weight_down" in evidence
                else (-1 if "weight_up" in evidence else 0)
            )
            waist_direction = (
                1 if "waist_down" in evidence
                else (-1 if "waist_up" in evidence else 0)
            )
            # DHS quality vote direction
            dhs_direction = (
                1 if any(
                    e in ("dhs_fat_loss_good", "dhs_fat_loss_with_muscle_risk")
                    for e in evidence
                )
                else 0
            )

            # If weight+waist agree and DHS disagrees → DHS unreliable
            if (
                weight_direction != 0
                and weight_direction == waist_direction
                and dhs_direction != 0
                and dhs_direction != weight_direction
            ):
                fat_confidence = min(fat_confidence, 0.4)
                adjustments.append("rule4_scale_overridden_by_consensus")

    # ── Rule 5: Creatine suppression ──
    if sufficiency["creatine_within_21d"] and fat_loss_status == "reversed":
        fat_loss_status = "not_confirmed"
        fat_confidence = min(fat_confidence, 0.3)
        if "creatine_water_retention" not in evidence:
            evidence.append("creatine_water_retention")
        adjustments.append("rule5_creatine_suppression")

    return fat_loss_status, fat_confidence, adjustments


# =========================================================================
# Muscle Assessment (Weighted Voting System)
# =========================================================================


def _assess_muscle(today, summaries, user, as_of_date, sufficiency):
    """Multi-source weighted voting for muscle status.

    Returns: (status_str, evidence_list, confidence_float)
    """
    weighted_votes = []
    evidence = []

    # ── Source 1: Muscle preservation status ──
    mps = today.get("muscle_preservation_status")
    if mps == "HIGH_QUALITY":
        weighted_votes.append((+1, CONFIDENCE_MUSCLE_PRESERVATION, "preservation_high"))
        evidence.append("preservation_high")
    elif mps == "MUSCLE_RISK":
        weighted_votes.append((-1, CONFIDENCE_MUSCLE_PRESERVATION, "preservation_risk"))
        evidence.append("preservation_risk")
    elif mps == "MODERATE_QUALITY":
        evidence.append("preservation_moderate")

    # ── Source 2: Muscle loss risk score ──
    mlr = today.get("muscle_loss_risk_score")
    if mlr is not None:
        if mlr < 30:
            weighted_votes.append((+1, CONFIDENCE_MUSCLE_RISK_SCORE, "low_risk_score"))
            evidence.append("low_risk_score")
        elif mlr > 70:
            weighted_votes.append((-1, CONFIDENCE_MUSCLE_RISK_SCORE, "high_risk_score"))
            evidence.append("high_risk_score")

    # ── Source 3: Recomposition flag ──
    if today.get("recomposition_flag_14d"):
        weighted_votes.append((+1, CONFIDENCE_RECOMP_FLAG, "recomp_flag"))
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
        weighted_votes.append((+1, CONFIDENCE_MUSCLE_TAPE, "measurements_growing"))
        evidence.append("measurements_growing")
    elif m_down >= 2:
        weighted_votes.append((-1, CONFIDENCE_MUSCLE_TAPE, "measurements_shrinking"))
        evidence.append("measurements_shrinking")

    # ── Weighted vote tally ──
    if not weighted_votes:
        return "unclear", evidence, 0.0

    weighted_sum = sum(d * w for d, w, _ in weighted_votes)
    total_weight = sum(w for _, w, _ in weighted_votes)
    ratio = weighted_sum / total_weight if total_weight > 0 else 0.0

    result_direction = 1 if ratio > 0 else (-1 if ratio < 0 else 0)
    agreeing = [w for d, w, _ in weighted_votes if d == result_direction]
    muscle_confidence = sum(agreeing) / len(agreeing) if agreeing else 0.0

    if ratio >= 0.5:
        return "likely", evidence, muscle_confidence
    elif ratio > -0.5:
        return "unclear", evidence, muscle_confidence
    else:
        return "unlikely", evidence, muscle_confidence


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
    """Waist delta over 28 days.  Returns None when insufficient data."""
    delta, ok = _measurement_trend(user, "waist", as_of_date, days=28)
    return round(delta, 2) if ok else None


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
        "waist_trend": None,
        "confidence": "low",
        # New fields
        "fat_confidence": 0.0,
        "muscle_confidence": 0.0,
        "sufficiency": None,
        "conflict_adjustments": [],
        # Velocity
        "fat_loss_rate_lbs_per_week": None,
        "fat_loss_speed": None,
        "waist_rate_per_week": None,
        # Plateau
        "plateau_status": "none",
        "plateau_type": None,
        "plateau_days": 0,
        # Verdict
        "verdict": "no_data",
    }
