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
    except Exception:
        logger.error("Failed to compute health trends for CoS", exc_info=True)

    # Correlations
    try:
        from apps.health.services.correlation_service import CorrelationService
        result["correlations"] = CorrelationService.compute(user, today_date)
    except Exception:
        logger.error("Failed to compute health correlations for CoS", exc_info=True)

    # Protein intelligence
    try:
        from apps.health.services.protein_service import ProteinService
        coaching = ProteinService.get_coaching(user, today_date)
        weekly = ProteinService.get_weekly_summary(user, today_date)
        result["protein_intelligence"] = {
            "coaching": coaching,
            "weekly_summary": {
                k: v for k, v in weekly.items()
                if k != "daily_detail"  # exclude chart data from CoS
            } if weekly else {},
            "target_g": float(ProteinService.calculate_target(user, today_date) or 0),
        }
    except Exception:
        logger.error("Failed to compute protein intelligence for CoS", exc_info=True)

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
            protein_str = f"Protein: {today['protein_g']:.0f}g"
            if today.get("protein_target_g"):
                ratio = today['protein_g'] / today['protein_target_g'] * 100
                protein_str += f" ({ratio:.0f}% of {today['protein_target_g']:.0f}g target)"
            parts.append(protein_str)

    # Protein coaching
    protein_intel = intel.get("protein_intelligence", {})
    coaching = protein_intel.get("coaching", {})
    if coaching and coaching.get("severity") in ("warning", "nudge"):
        parts.append(f"Protein: {coaching['message']}")

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
