"""
Health Score Service — composite 0-100 score, longevity-first.

Weights:
    Sleep consistency:     20
    Recovery score:        20
    Glucose stability:     15
    Weight/body comp:      15
    Workout consistency:   10
    Nutrition consistency: 10
    Activity level:        10

Missing signals reduce the denominator (not the score) —
don't punish users who haven't connected a CGM.

Usage:
    from apps.health.services.health_score import HealthScoreService
    score, drivers = HealthScoreService.compute(user, date.today())
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q

logger = logging.getLogger(__name__)

# Domain weights (must sum to 100)
DOMAIN_WEIGHTS = {
    "sleep": 20,
    "recovery": 20,
    "glucose": 15,
    "weight_trend": 15,
    "workout": 10,
    "nutrition": 10,
    "activity": 10,
}


class HealthScoreService:
    """
    Compute a composite health score (0-100) with explainable drivers.

    Returns (score: int or None, drivers: dict).
    """

    @staticmethod
    def compute(user, target_date):
        """
        Compute health score for the given date.

        Uses 7-day rolling data for consistency metrics.

        Returns:
            (score: int | None, drivers: dict)
        """
        from apps.health.models import DailyHealthSummary
        from apps.health.services.baseline_policy import BaselinePolicy

        if not BaselinePolicy.baseline_ready(user, target_date):
            msg = BaselinePolicy.baseline_message(user, target_date)
            return None, {
                "status": "baseline_collecting",
                "message": msg or "Collecting baseline data",
            }

        # Get last 7 days of summaries
        week_start = target_date - timedelta(days=6)
        summaries = list(
            DailyHealthSummary.objects
            .filter(user=user, summary_date__gte=week_start, summary_date__lte=target_date)
            .order_by("summary_date")
        )

        if not summaries:
            return None, {"status": "no_data", "message": "No data available"}

        today = summaries[-1] if summaries[-1].summary_date == target_date else None

        domain_scores = {}
        active_weights = {}

        # --- Sleep Consistency (20) ---
        sleep_result = HealthScoreService._score_sleep_consistency(summaries)
        if sleep_result is not None:
            domain_scores["sleep"] = sleep_result
            active_weights["sleep"] = DOMAIN_WEIGHTS["sleep"]

        # --- Recovery (20) ---
        if today and today.recovery_score is not None:
            domain_scores["recovery"] = {
                "score": today.recovery_score,
                "detail": f"Recovery score: {today.recovery_score}/100",
            }
            active_weights["recovery"] = DOMAIN_WEIGHTS["recovery"]

        # --- Glucose Stability (15) ---
        glucose_result = HealthScoreService._score_glucose_stability(summaries)
        if glucose_result is not None:
            domain_scores["glucose"] = glucose_result
            active_weights["glucose"] = DOMAIN_WEIGHTS["glucose"]

        # --- Weight Trend (15) ---
        weight_result = HealthScoreService._score_weight_trend(user, target_date)
        if weight_result is not None:
            domain_scores["weight_trend"] = weight_result
            active_weights["weight_trend"] = DOMAIN_WEIGHTS["weight_trend"]

        # --- Workout Consistency (10) ---
        workout_result = HealthScoreService._score_workout_consistency(summaries)
        if workout_result is not None:
            domain_scores["workout"] = workout_result
            active_weights["workout"] = DOMAIN_WEIGHTS["workout"]

        # --- Nutrition Consistency (10) ---
        nutrition_result = HealthScoreService._score_nutrition_consistency(summaries, user)
        if nutrition_result is not None:
            domain_scores["nutrition"] = nutrition_result
            active_weights["nutrition"] = DOMAIN_WEIGHTS["nutrition"]

        # --- Activity Level (10) ---
        activity_result = HealthScoreService._score_activity(summaries)
        if activity_result is not None:
            domain_scores["activity"] = activity_result
            active_weights["activity"] = DOMAIN_WEIGHTS["activity"]

        if not active_weights:
            return None, {"status": "insufficient_data"}

        # Normalize and compute final score
        total_weight = sum(active_weights.values())
        final_score = sum(
            domain_scores[k]["score"] * (active_weights[k] / total_weight)
            for k in active_weights
        )
        final_score = max(0, min(100, int(round(final_score))))

        # Identify strongest and weakest
        sorted_domains = sorted(
            domain_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )

        strongest = sorted_domains[0] if sorted_domains else None
        weakest = sorted_domains[-1] if len(sorted_domains) > 1 else None

        # Compute delta vs last week
        prev_week_start = target_date - timedelta(days=13)
        prev_week_end = target_date - timedelta(days=7)
        prev_summary = (
            DailyHealthSummary.objects
            .filter(
                user=user,
                summary_date__gte=prev_week_start,
                summary_date__lte=prev_week_end,
                health_score__isnull=False,
            )
            .aggregate(avg=Avg("health_score"))
        )
        prev_avg = prev_summary.get("avg")
        delta_vs_last_week = None
        if prev_avg is not None:
            delta_vs_last_week = final_score - int(round(prev_avg))

        drivers = {
            "domains": {
                k: {
                    "score": v["score"],
                    "weight": active_weights.get(k, 0),
                    "detail": v["detail"],
                }
                for k, v in domain_scores.items()
            },
            "missing_signals": [
                k for k in DOMAIN_WEIGHTS if k not in active_weights
            ],
            "strongest_positive_signal": (
                f"{strongest[0]}: {strongest[1]['detail']}" if strongest else ""
            ),
            "primary_risk": (
                f"{weakest[0]}: {weakest[1]['detail']}"
                if weakest and weakest[1]["score"] < 60
                else "No significant risks"
            ),
            "immediate_focus": HealthScoreService._immediate_focus(domain_scores),
            "delta_vs_last_week": delta_vs_last_week,
            "status": "computed",
        }

        return final_score, drivers

    @staticmethod
    def _score_sleep_consistency(summaries):
        """Score based on 7-day sleep consistency."""
        sleep_days = [s for s in summaries if s.sleep_hours is not None]
        if not sleep_days:
            return None

        hours_list = [float(s.sleep_hours) for s in sleep_days]
        avg_hours = sum(hours_list) / len(hours_list)
        days_above_7 = sum(1 for h in hours_list if h >= 7)
        consistency_pct = days_above_7 / len(hours_list) * 100

        # Average sleep quality
        quality_list = [s.sleep_quality_score for s in sleep_days if s.sleep_quality_score]
        avg_quality = sum(quality_list) / len(quality_list) if quality_list else 50

        # Score: 50% duration, 30% consistency, 20% quality
        duration_score = min(100, int(avg_hours / 7.5 * 100))
        consistency_score = int(consistency_pct)
        quality_score = int(avg_quality)

        score = int(duration_score * 0.5 + consistency_score * 0.3 + quality_score * 0.2)
        score = max(0, min(100, score))

        return {
            "score": score,
            "detail": f"Avg {avg_hours:.1f}h, {days_above_7}/{len(sleep_days)} nights ≥7h",
        }

    @staticmethod
    def _score_glucose_stability(summaries):
        """Score glucose stability over the week."""
        glucose_days = [s for s in summaries if s.glucose_avg is not None]
        if not glucose_days:
            return None

        avg_glucose = sum(float(s.glucose_avg) for s in glucose_days) / len(glucose_days)
        tir_values = [float(s.time_in_range_pct) for s in glucose_days if s.time_in_range_pct]
        cv_values = [float(s.glucose_variability) for s in glucose_days if s.glucose_variability]

        score = 70  # Default

        # Time in range score
        if tir_values:
            avg_tir = sum(tir_values) / len(tir_values)
            if avg_tir >= 85:
                tir_score = 95
            elif avg_tir >= 70:
                tir_score = 75
            elif avg_tir >= 55:
                tir_score = 50
            else:
                tir_score = 30
            score = tir_score

        # Variability penalty
        if cv_values:
            avg_cv = sum(cv_values) / len(cv_values)
            if avg_cv > 50:
                score = max(0, score - 20)
            elif avg_cv > 36:
                score = max(0, score - 10)

        return {
            "score": max(0, min(100, score)),
            "detail": f"Avg glucose {avg_glucose:.0f} mg/dL, {len(glucose_days)} days tracked",
        }

    @staticmethod
    def _score_weight_trend(user, target_date):
        """Score weight trend direction relative to goal."""
        from apps.health.models import DailyHealthSummary, HealthProfile

        # Get weight data for last 28 days
        start = target_date - timedelta(days=27)
        weights = list(
            DailyHealthSummary.objects
            .filter(user=user, summary_date__gte=start, summary_date__lte=target_date, weight__isnull=False)
            .order_by("summary_date")
            .values_list("weight", flat=True)
        )

        if len(weights) < 3:
            return None

        # Simple trend: compare first third average vs last third average
        third = max(1, len(weights) // 3)
        first_avg = sum(float(w) for w in weights[:third]) / third
        last_avg = sum(float(w) for w in weights[-third:]) / third
        change = last_avg - first_avg

        # Check if user has a weight goal
        try:
            profile = HealthProfile.objects.get(user=user)
            goal = float(profile.weight_goal) if profile.weight_goal else None
            goal_unit = profile.weight_goal_unit
        except HealthProfile.DoesNotExist:
            goal = None
            goal_unit = "lb"

        score = 70  # Default neutral
        detail = ""

        if goal:
            # Convert goal to lbs if needed
            if goal_unit == "kg":
                goal = goal * 2.20462

            current = float(weights[-1])
            if current > goal:
                # Need to lose weight
                if change < -0.5:  # Losing weight
                    weekly_rate = change / 4  # Over ~4 weeks
                    if -2 <= weekly_rate <= -0.5:
                        score = 90
                        detail = f"Losing {abs(weekly_rate):.1f} lbs/week toward goal"
                    elif weekly_rate < -2:
                        score = 65
                        detail = f"Losing too fast ({abs(weekly_rate):.1f} lbs/week)"
                    else:
                        score = 75
                        detail = f"Slow but steady loss"
                elif change > 1:
                    score = 35
                    detail = f"Gaining {change:.1f} lbs (goal: lose)"
                else:
                    score = 55
                    detail = f"Weight plateau — {current:.1f} lbs, goal: {goal:.0f}"
            elif current < goal:
                # Need to gain
                if change > 0.5:
                    score = 85
                    detail = f"Gaining toward goal"
                else:
                    score = 55
                    detail = f"Below target, not gaining"
            else:
                score = 90
                detail = "At goal weight"
        else:
            # No goal: just report trend
            if abs(change) < 1:
                score = 75
                detail = f"Weight stable ({float(weights[-1]):.1f} lbs)"
            else:
                direction = "down" if change < 0 else "up"
                score = 65
                detail = f"Weight trending {direction} ({change:+.1f} lbs over 4 weeks)"

        return {"score": max(0, min(100, score)), "detail": detail}

    @staticmethod
    def _score_workout_consistency(summaries):
        """Score workout frequency and consistency."""
        workout_days = sum(1 for s in summaries if s.workout_count > 0)
        total_days = len(summaries)

        if total_days == 0:
            return None

        # Assume target is 4 workouts per 7 days
        target_ratio = 4 / 7
        actual_ratio = workout_days / total_days

        if actual_ratio >= target_ratio:
            score = min(100, int(80 + (actual_ratio - target_ratio) * 100))
        elif actual_ratio >= target_ratio * 0.75:
            score = 65
        elif actual_ratio >= target_ratio * 0.5:
            score = 45
        elif actual_ratio > 0:
            score = 30
        else:
            score = 15

        return {
            "score": max(0, min(100, score)),
            "detail": f"{workout_days} workouts in {total_days} days",
        }

    @staticmethod
    def _score_nutrition_consistency(summaries, user):
        """Score nutrition tracking and quality."""
        logged_days = sum(1 for s in summaries if s.nutrition_logged)
        total_days = len(summaries)

        if total_days == 0:
            return None

        tracking_pct = logged_days / total_days * 100

        # Base score on tracking consistency
        if tracking_pct >= 85:
            score = 85
        elif tracking_pct >= 70:
            score = 70
        elif tracking_pct >= 50:
            score = 50
        elif tracking_pct > 0:
            score = 30
        else:
            return None  # No tracking data at all

        # Protein adequacy bonus/penalty
        protein_days = [s for s in summaries if s.protein_g and s.weight]
        if protein_days:
            avg_protein = sum(float(s.protein_g) for s in protein_days) / len(protein_days)
            avg_weight = sum(float(s.weight) for s in protein_days) / len(protein_days)
            if avg_weight > 0:
                protein_per_lb = avg_protein / avg_weight
                if protein_per_lb >= 0.8:
                    score = min(100, score + 10)
                elif protein_per_lb < 0.5:
                    score = max(0, score - 10)

        return {
            "score": max(0, min(100, score)),
            "detail": f"Tracked {logged_days}/{total_days} days",
        }

    @staticmethod
    def _score_activity(summaries):
        """Score daily activity based on steps and movement."""
        step_days = [s for s in summaries if s.steps is not None]
        if not step_days:
            return None

        avg_steps = sum(s.steps for s in step_days) / len(step_days)

        # Target: 10,000 steps
        if avg_steps >= 10000:
            score = 90
        elif avg_steps >= 7500:
            score = 75
        elif avg_steps >= 5000:
            score = 55
        elif avg_steps >= 2500:
            score = 35
        else:
            score = 20

        # Active minutes bonus
        active_days = [s for s in summaries if s.active_minutes is not None]
        if active_days:
            avg_active = sum(s.active_minutes for s in active_days) / len(active_days)
            if avg_active >= 30:
                score = min(100, score + 5)

        return {
            "score": max(0, min(100, score)),
            "detail": f"Avg {avg_steps:,.0f} steps/day",
        }

    @staticmethod
    def _immediate_focus(domain_scores):
        """Determine the single most impactful thing to focus on."""
        if not domain_scores:
            return "Start tracking your health data"

        # Find the weakest domain that's most impactful
        weighted = []
        for domain, result in domain_scores.items():
            weight = DOMAIN_WEIGHTS.get(domain, 5)
            impact = (100 - result["score"]) * weight
            weighted.append((domain, impact, result["score"]))

        weighted.sort(key=lambda x: x[1], reverse=True)
        top = weighted[0]

        focus_map = {
            "sleep": "Prioritize consistent 7+ hour sleep",
            "recovery": "Allow more recovery time between workouts",
            "glucose": "Focus on blood sugar stability",
            "weight_trend": "Align nutrition with weight goal",
            "workout": "Increase workout frequency",
            "nutrition": "Track meals consistently",
            "activity": "Increase daily step count",
        }
        return focus_map.get(top[0], f"Improve {top[0]}")
