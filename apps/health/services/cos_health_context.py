"""
CoS Health Context — provides multi-week health intelligence to CoS.

This replaces the snapshot-only health signals with trend-aware,
pattern-detecting context that enables CoS to make insightful observations.

Usage (from cos_context.py):
    from apps.health.services.cos_health_context import build_cos_health_intelligence
    health_intel = build_cos_health_intelligence(user)
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg

logger = logging.getLogger(__name__)


def build_cos_health_intelligence(user):
    """
    Build comprehensive health intelligence for CoS.

    Returns a dict optimized for CoS reasoning (no markdown, no formatting).
    Structure:
        today: today's snapshot
        scores: health_score, recovery_score + drivers
        trends_7d: 7-day rolling averages
        trends_28d: 28-day rolling averages
        strengths: list of current strengths
        weaknesses: list of current weaknesses
        risk_flags: list of risk alerts
        correlations: top 3 cross-domain correlations
        top_recommendation: single most important action
        baseline_status: baseline ready or collecting message
    """
    from apps.health.models import DailyHealthSummary
    from apps.health.services.baseline_policy import BaselinePolicy

    today_date = date.today()
    result = {
        "date": str(today_date),
        "baseline_ready": False,
        "today": None,
        "scores": {},
        "trends_7d": {},
        "trends_28d": {},
        "strengths": [],
        "weaknesses": [],
        "risk_flags": [],
        "correlations": [],
        "top_recommendation": "",
    }

    # Baseline status
    result["baseline_ready"] = BaselinePolicy.baseline_ready(user, today_date)
    if not result["baseline_ready"]:
        msg = BaselinePolicy.baseline_message(user, today_date)
        result["baseline_message"] = msg
        days = BaselinePolicy.baseline_days_available(user, today_date)
        result["baseline_days_available"] = days

    # Today's snapshot
    today_summary = (
        DailyHealthSummary.objects
        .filter(user=user, summary_date=today_date)
        .first()
    )
    if today_summary:
        result["today"] = _serialize_summary(today_summary)
        result["scores"] = {
            "health_score": today_summary.health_score,
            "health_drivers": today_summary.health_score_drivers,
            "recovery_score": today_summary.recovery_score,
            "recovery_drivers": today_summary.recovery_drivers,
        }

    # Yesterday (for comparison)
    yesterday = (
        DailyHealthSummary.objects
        .filter(user=user, summary_date=today_date - timedelta(days=1))
        .first()
    )
    if yesterday:
        result["yesterday"] = _serialize_summary(yesterday)

    # 7-day and 28-day trends
    try:
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer
        analysis = HealthTrendAnalyzer.analyze(user, today_date)
        result["trends_7d"] = analysis.get("rolling_7d", {})
        result["trends_28d"] = analysis.get("rolling_28d", {})
        result["strengths"] = analysis.get("strengths", [])
        result["weaknesses"] = analysis.get("weaknesses", [])
        result["risk_flags"] = analysis.get("risk_flags", [])
        result["top_recommendation"] = analysis.get("top_recommendation", "")
        result["trends"] = analysis.get("trends", {})
        result["coaching"] = analysis.get("coaching", {})
    except Exception:
        logger.error("Failed to compute health trends for CoS", exc_info=True)

    # Correlations
    try:
        from apps.health.services.correlation_service import CorrelationService
        result["correlations"] = CorrelationService.compute(user, today_date)
    except Exception:
        logger.error("Failed to compute health correlations for CoS", exc_info=True)

    # Protein intelligence (LBM-aware)
    try:
        from apps.health.services.protein_service import ProteinService
        coaching = ProteinService.get_coaching(user, today_date)
        weekly = ProteinService.get_weekly_summary(user, today_date)
        target_info = ProteinService.calculate_target(user, today_date)

        # Extract weekly average fields for CoS (the key fix for weekly questions)
        weekly_avg_g = None
        weekly_consistency_pct = None
        weekly_gap_g = None
        weekly_avg_ratio = None
        target_g_val = float(target_info["target_g"]) if target_info else 0
        if weekly and weekly.get("status") == "ok":
            weekly_avg_g = weekly.get("avg_consumed_g")
            weekly_avg_ratio = weekly.get("avg_ratio")
            weekly_consistency_pct = weekly.get("consistency_pct")
            if weekly_avg_g is not None and target_g_val:
                weekly_gap_g = round(target_g_val - weekly_avg_g, 1)

        # IMPORTANT: Only expose pre-calculated evaluation fields to CoS.
        # Do NOT expose raw weekly_summary dict — the LLM will attempt its
        # own math (e.g., multiplying avg × days) and produce wrong answers.
        result["protein_intelligence"] = {
            "coaching": coaching,
            # Today's target
            "target_g": target_g_val,
            "method": target_info["method"] if target_info else None,
            "lean_body_mass": target_info["lbm"] if target_info else None,
            "workout_day": target_info["workout_day"] if target_info else False,
            "multiplier": target_info["multiplier"] if target_info else None,
            # Weekly protein evaluation (7-day AVERAGE vs daily target)
            # These are the ONLY weekly fields CoS should use.
            "protein_avg_7d": weekly_avg_g,
            "protein_consistency_pct": weekly_consistency_pct,
            "protein_gap_g": weekly_gap_g,
            "protein_avg_ratio": weekly_avg_ratio,
        }
    except Exception:
        logger.error("Failed to compute protein intelligence for CoS", exc_info=True)

    # Body composition intelligence (read from DailyHealthSummary ONLY)
    # These values are pre-computed by BodyCompositionIntelligence at rollup time.
    if today_summary:
        def _dec(val):
            return float(val) if val is not None else None

        result["body_comp_intelligence"] = {
            "fat_mass": _dec(today_summary.fat_mass),
            "fat_loss_quality_label": today_summary.fat_loss_quality_label or None,
            "fat_loss_ratio_14d": _dec(today_summary.fat_loss_ratio_14d),
            "recomposition_flag_14d": today_summary.recomposition_flag_14d,
            "plateau_status": today_summary.plateau_status or None,
            "fat_loss_speed_pct_per_week": _dec(today_summary.fat_loss_speed_pct_per_week),
            "fat_loss_speed_label": today_summary.fat_loss_speed_label or None,
            "muscle_loss_risk_score": today_summary.muscle_loss_risk_score,
            "muscle_loss_risk_level": today_summary.muscle_loss_risk_level or None,
            "body_comp_drivers": today_summary.body_comp_drivers or {},
            # Plateau Early Warning
            "plateau_risk_score": today_summary.plateau_risk_score,
            "plateau_risk_label": today_summary.plateau_risk_label or None,
            "plateau_prediction_window_days": today_summary.plateau_prediction_window_days,
            # Fat Loss Phase
            "fat_loss_phase": today_summary.fat_loss_phase or None,
            "phase_confidence": today_summary.phase_confidence,
            "phase_start_date": (
                str(today_summary.phase_start_date)
                if today_summary.phase_start_date else None
            ),
            # Muscle Preservation (alias)
            "muscle_preservation_status": today_summary.muscle_preservation_status or None,
            # Timestamp for "last updated" in CoS status responses
            "last_computed": (
                today_summary.last_computed.isoformat()
                if today_summary.last_computed else str(today_summary.summary_date)
            ),
        }

    return result


def _serialize_summary(summary):
    """Serialize a DailyHealthSummary to a plain dict for CoS context."""
    def _dec(val):
        return float(val) if val is not None else None

    return {
        "date": str(summary.summary_date),
        "sleep_hours": _dec(summary.sleep_hours),
        "sleep_quality_score": summary.sleep_quality_score,
        "sleep_debt_minutes": summary.sleep_debt_minutes,
        "deep_sleep_minutes": summary.deep_sleep_minutes,
        "rem_sleep_minutes": summary.rem_sleep_minutes,
        "resting_hr": summary.resting_hr,
        "hrv": _dec(summary.hrv),
        "steps": summary.steps,
        "active_minutes": summary.active_minutes,
        "calories_burned": summary.calories_burned,
        "workout_count": summary.workout_count,
        "workout_minutes": summary.workout_minutes,
        "training_load": _dec(summary.training_load),
        "weight": _dec(summary.weight),
        "body_fat_pct": _dec(summary.body_fat_pct),
        "glucose_avg": _dec(summary.glucose_avg),
        "glucose_variability": _dec(summary.glucose_variability),
        "time_in_range_pct": _dec(summary.time_in_range_pct),
        "calories_consumed": summary.calories_consumed,
        "protein_g": _dec(summary.protein_g),
        "protein_target_g": _dec(summary.protein_target_g),
        "protein_consumed_g": _dec(summary.protein_consumed_g),
        "protein_ratio": _dec(summary.protein_ratio),
        "protein_score": summary.protein_score,
        "protein_per_lb": _dec(summary.protein_per_lb),
        "protein_method": summary.protein_method,
        "carbs_g": _dec(summary.carbs_g),
        "fat_g": _dec(summary.fat_g),
        "water_oz": _dec(summary.water_oz),
        "nutrition_logged": summary.nutrition_logged,
        "medication_adherence_pct": _dec(summary.medication_adherence_pct),
        "fasting_hours": _dec(summary.fasting_hours),
        "caffeine_mg": _dec(summary.caffeine_mg),
        "mindful_minutes": summary.mindful_minutes,
        "health_score": summary.health_score,
        "recovery_score": summary.recovery_score,
        "data_completeness_pct": _dec(summary.data_completeness_pct),
        "signals_present": summary.signals_present,
    }


def build_cos_health_summary_text(user):
    """
    Build a concise text summary for inline CoS context injection.

    Returns a compact string (not markdown) that CoS can reason about.
    """
    intel = build_cos_health_intelligence(user)

    parts = []

    # Scores
    scores = intel.get("scores", {})
    hs = scores.get("health_score")
    rs = scores.get("recovery_score")
    if hs is not None:
        parts.append(f"Health score: {hs}/100")
    if rs is not None:
        recovery_drivers = scores.get("recovery_drivers", {})
        status = recovery_drivers.get("status", "")
        parts.append(f"Recovery: {rs}/100 ({status})")

    if not intel.get("baseline_ready"):
        parts.append(intel.get("baseline_message", "Collecting baseline data"))

    # Today's key metrics
    today = intel.get("today", {})
    if today:
        if today.get("sleep_hours"):
            parts.append(f"Sleep: {today['sleep_hours']:.1f}h")
        if today.get("steps"):
            parts.append(f"Steps: {today['steps']:,}")
        if today.get("workout_count"):
            parts.append(f"Workouts today: {today['workout_count']}")
        if today.get("calories_consumed"):
            parts.append(f"Calories: {today['calories_consumed']}")
        if today.get("protein_g"):
            protein_str = f"Protein today: {today['protein_g']:.0f}g"
            if today.get("protein_target_g"):
                ratio = today['protein_g'] / today['protein_target_g'] * 100
                protein_str += f" ({ratio:.0f}% of {today['protein_target_g']:.0f}g daily target)"
            parts.append(protein_str)

    # Protein weekly evaluation (7-day AVERAGE, never totals)
    protein_intel = intel.get("protein_intelligence", {})
    p_avg = protein_intel.get("protein_avg_7d")
    p_target = protein_intel.get("target_g")
    p_ratio = protein_intel.get("protein_avg_ratio")
    if p_avg and p_target:
        pct = round(p_ratio * 100) if p_ratio else round(p_avg / p_target * 100)
        gap = round(p_target - p_avg, 1)
        p_method = protein_intel.get("method", "")
        method_note = " (LBM-based)" if p_method == "lean_body_mass" else ""
        parts.append(
            f"Protein 7d avg: {p_avg:.0f}g/day "
            f"({pct}% of {p_target:.0f}g daily target{method_note})"
        )
        if gap > 0:
            parts.append(f"Protein gap: {gap:.0f}g/day below target")

    # Protein coaching
    coaching = protein_intel.get("coaching", {})
    if coaching and coaching.get("severity") in ("warning", "nudge"):
        parts.append(f"Protein: {coaching['message']}")

    # Body composition intelligence
    body_comp = intel.get("body_comp_intelligence", {})
    if body_comp:
        fl_label = body_comp.get("fat_loss_quality_label")
        fl_ratio = body_comp.get("fat_loss_ratio_14d")
        if fl_label and fl_label != "INSUFFICIENT_DATA":
            ratio_str = f" (ratio {fl_ratio:.2f})" if fl_ratio else ""
            parts.append(f"Fat loss quality: {fl_label}{ratio_str}")

        if body_comp.get("recomposition_flag_14d"):
            parts.append("Body recomposition detected")

        plateau = body_comp.get("plateau_status")
        if plateau and plateau not in ("INSUFFICIENT_DATA", ""):
            parts.append(f"Plateau status: {plateau}")

        speed_label = body_comp.get("fat_loss_speed_label")
        speed_pct = body_comp.get("fat_loss_speed_pct_per_week")
        if speed_label and speed_label not in ("INSUFFICIENT_DATA", ""):
            speed_str = f" ({speed_pct:.1f}%/week)" if speed_pct else ""
            parts.append(f"Fat loss speed: {speed_label}{speed_str}")

        risk_level = body_comp.get("muscle_loss_risk_level")
        if risk_level and risk_level != "LOW":
            parts.append(f"Muscle loss risk: {risk_level}")

        # Plateau early warning
        pr_label = body_comp.get("plateau_risk_label")
        pr_score = body_comp.get("plateau_risk_score")
        pr_window = body_comp.get("plateau_prediction_window_days")
        if pr_label and pr_label != "LOW":
            window_str = f", ~{pr_window} days" if pr_window is not None else ""
            parts.append(f"Plateau risk: {pr_label} (score {pr_score}{window_str})")

        # Fat loss phase
        phase = body_comp.get("fat_loss_phase")
        phase_conf = body_comp.get("phase_confidence")
        if phase:
            conf_str = f" ({phase_conf}% confidence)" if phase_conf else ""
            parts.append(f"Fat loss phase: {phase}{conf_str}")

        # Muscle preservation status
        mp_status = body_comp.get("muscle_preservation_status")
        if mp_status and mp_status != "INSUFFICIENT_DATA":
            parts.append(f"Muscle preservation: {mp_status}")

    # 7-day trends
    t7 = intel.get("trends_7d", {})
    if t7:
        if t7.get("sleep_hours"):
            parts.append(f"7d avg sleep: {t7['sleep_hours']:.1f}h")
        if t7.get("steps"):
            parts.append(f"7d avg steps: {t7['steps']:,.0f}")

    # Strengths / weaknesses
    strengths = intel.get("strengths", [])
    weaknesses = intel.get("weaknesses", [])
    risk_flags = intel.get("risk_flags", [])

    if strengths:
        parts.append(f"Strengths: {'; '.join(strengths[:2])}")
    if weaknesses:
        parts.append(f"Watch: {'; '.join(weaknesses[:2])}")
    if risk_flags:
        flags = [r["message"] for r in risk_flags[:2]]
        parts.append(f"Risks: {'; '.join(flags)}")

    # Top recommendation
    rec = intel.get("top_recommendation")
    if rec:
        parts.append(f"Focus: {rec}")

    # Correlations
    corrs = intel.get("correlations", [])
    if corrs:
        top = corrs[0]
        parts.append(f"Pattern: {top['interpretation']}")

    return " | ".join(parts) if parts else "No health intelligence data available"
