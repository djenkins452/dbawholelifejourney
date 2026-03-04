"""
Health Trend Analyzer — detects multi-week patterns, plateaus, and risks.

Analyzes 7/28-day rolling windows from DailyHealthSummary to identify
strengths, weaknesses, and actionable risk flags.

Usage:
    from apps.health.services.trend_analyzer import HealthTrendAnalyzer
    analysis = HealthTrendAnalyzer.analyze(user, date.today())
"""

import logging
import statistics
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q

logger = logging.getLogger(__name__)


class HealthTrendAnalyzer:
    """Detect multi-week health patterns from DailyHealthSummary data."""

    @staticmethod
    def analyze(user, target_date):
        """
        Full trend analysis for a user.

        Returns:
            dict with keys:
                strengths: list of strength strings
                weaknesses: list of weakness strings
                risk_flags: list of risk flag dicts
                top_recommendation: string
                rolling_7d: dict of 7-day averages
                rolling_28d: dict of 28-day averages
                trends: dict of trend directions per domain
        """
        from apps.health.models import DailyHealthSummary

        # Load 56 days of data for 28d comparison + prior 28d
        lookback = target_date - timedelta(days=55)
        summaries = list(
            DailyHealthSummary.objects
            .filter(user=user, summary_date__gte=lookback, summary_date__lte=target_date)
            .order_by("summary_date")
        )

        if len(summaries) < 7:
            return {
                "strengths": [],
                "weaknesses": [],
                "risk_flags": [],
                "top_recommendation": "Keep tracking — more data needed for trend analysis",
                "rolling_7d": {},
                "rolling_28d": {},
                "trends": {},
            }

        # Split into periods
        recent_7 = [s for s in summaries if s.summary_date > target_date - timedelta(days=7)]
        recent_28 = [s for s in summaries if s.summary_date > target_date - timedelta(days=28)]
        prior_28 = [
            s for s in summaries
            if target_date - timedelta(days=56) < s.summary_date <= target_date - timedelta(days=28)
        ]

        rolling_7d = HealthTrendAnalyzer._compute_rolling(recent_7)
        rolling_28d = HealthTrendAnalyzer._compute_rolling(recent_28)

        strengths = []
        weaknesses = []
        risk_flags = []
        trends = {}

        # Detect patterns
        HealthTrendAnalyzer._detect_weight_patterns(
            recent_28, prior_28, user, target_date, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_sleep_patterns(
            recent_7, recent_28, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_nutrition_patterns(
            recent_7, recent_28, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_workout_patterns(
            recent_7, recent_28, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_glucose_patterns(
            recent_7, recent_28, prior_28, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_activity_patterns(
            recent_7, recent_28, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_medication_patterns(
            recent_7, recent_28, strengths, weaknesses, risk_flags, trends
        )
        HealthTrendAnalyzer._detect_protein_patterns(
            recent_7, recent_28, user, target_date, strengths, weaknesses, risk_flags, trends
        )

        # Top recommendation: highest-impact risk flag or biggest weakness
        top_rec = HealthTrendAnalyzer._determine_top_recommendation(
            risk_flags, weaknesses, strengths
        )

        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "risk_flags": risk_flags,
            "top_recommendation": top_rec,
            "rolling_7d": rolling_7d,
            "rolling_28d": rolling_28d,
            "trends": trends,
        }

    @staticmethod
    def _compute_rolling(summaries):
        """Compute rolling averages from a list of summaries."""
        if not summaries:
            return {}

        def safe_avg(values):
            valid = [v for v in values if v is not None]
            return round(sum(float(v) for v in valid) / len(valid), 2) if valid else None

        return {
            "sleep_hours": safe_avg([s.sleep_hours for s in summaries]),
            "sleep_quality": safe_avg([s.sleep_quality_score for s in summaries]),
            "steps": safe_avg([s.steps for s in summaries]),
            "active_minutes": safe_avg([s.active_minutes for s in summaries]),
            "calories_consumed": safe_avg([s.calories_consumed for s in summaries]),
            "protein_g": safe_avg([s.protein_g for s in summaries]),
            "weight": safe_avg([s.weight for s in summaries]),
            "glucose_avg": safe_avg([s.glucose_avg for s in summaries]),
            "hrv": safe_avg([s.hrv for s in summaries]),
            "resting_hr": safe_avg([s.resting_hr for s in summaries]),
            "recovery_score": safe_avg([s.recovery_score for s in summaries]),
            "health_score": safe_avg([s.health_score for s in summaries]),
            "protein_consumed_g": safe_avg([s.protein_consumed_g or s.protein_g for s in summaries]),
            "protein_target_g": safe_avg([s.protein_target_g for s in summaries]),
            "protein_ratio": safe_avg([s.protein_ratio for s in summaries]),
            "protein_score": safe_avg([s.protein_score for s in summaries]),
            "protein_per_lb": safe_avg([s.protein_per_lb for s in summaries]),
            "workout_days": sum(1 for s in summaries if s.workout_count > 0),
            "nutrition_logged_days": sum(1 for s in summaries if s.nutrition_logged),
            "total_days": len(summaries),
        }

    # --- Pattern Detectors ---

    @staticmethod
    def _detect_weight_patterns(recent_28, prior_28, user, target_date,
                                 strengths, weaknesses, risk_flags, trends):
        """Detect weight loss/gain plateaus and trends."""
        weights = [float(s.weight) for s in recent_28 if s.weight]
        if len(weights) < 5:
            return

        # Linear regression approximation: slope over time
        n = len(weights)
        x_mean = (n - 1) / 2
        y_mean = sum(weights) / n
        numerator = sum((i - x_mean) * (weights[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        weekly_change = slope * 7

        if weekly_change < -0.3:
            trends["weight"] = "declining"
            if -2.0 <= weekly_change <= -0.5:
                strengths.append(f"Healthy weight loss pace ({abs(weekly_change):.1f} lbs/week)")
            elif weekly_change < -2.0:
                risk_flags.append({
                    "domain": "weight",
                    "severity": "warning",
                    "message": f"Rapid weight loss ({abs(weekly_change):.1f} lbs/week) — risk of muscle loss",
                })
        elif weekly_change > 0.3:
            trends["weight"] = "increasing"
            weaknesses.append(f"Weight trending up (+{weekly_change:.1f} lbs/week)")
        else:
            trends["weight"] = "stable"

        # Plateau detection: <0.5 lb change over 10-14 days
        if len(weights) >= 10:
            last_10 = weights[-10:]
            range_10d = max(last_10) - min(last_10)
            if range_10d < 1.0 and abs(weekly_change) < 0.3:
                # Check if user should be losing weight
                from apps.health.models import HealthProfile
                try:
                    profile = HealthProfile.objects.get(user=user)
                    if profile.weight_goal and float(profile.weight_goal) < weights[-1]:
                        risk_flags.append({
                            "domain": "weight",
                            "severity": "info",
                            "message": f"Weight plateau detected — {range_10d:.1f} lb range over 10 days",
                        })
                except HealthProfile.DoesNotExist:
                    pass

    @staticmethod
    def _detect_sleep_patterns(recent_7, recent_28, strengths, weaknesses,
                                risk_flags, trends):
        """Detect sleep debt, inconsistency, and quality patterns."""
        sleep_7d = [s for s in recent_7 if s.sleep_hours is not None]
        sleep_28d = [s for s in recent_28 if s.sleep_hours is not None]

        if not sleep_7d:
            return

        avg_7d = sum(float(s.sleep_hours) for s in sleep_7d) / len(sleep_7d)
        below_7_count = sum(1 for s in sleep_7d if float(s.sleep_hours) < 7)

        # Sleep debt pattern
        if below_7_count >= 3:
            risk_flags.append({
                "domain": "sleep",
                "severity": "warning",
                "message": f"Sleep debt pattern: {below_7_count}/{len(sleep_7d)} nights below 7 hours",
            })
            weaknesses.append(f"Averaging {avg_7d:.1f}h sleep (target: 7-8h)")
            trends["sleep"] = "declining"
        elif avg_7d >= 7.0:
            strengths.append(f"Good sleep average ({avg_7d:.1f}h)")
            trends["sleep"] = "stable"
        else:
            trends["sleep"] = "stable"

        # Bedtime consistency (check std dev of sleep_hours as proxy)
        if len(sleep_28d) >= 14:
            hours_list = [float(s.sleep_hours) for s in sleep_28d]
            try:
                std_dev = statistics.stdev(hours_list)
                if std_dev > 1.5:
                    weaknesses.append(f"Inconsistent sleep duration (±{std_dev:.1f}h variance)")
            except statistics.StatisticsError:
                pass

    @staticmethod
    def _detect_nutrition_patterns(recent_7, recent_28, strengths, weaknesses,
                                    risk_flags, trends):
        """Detect nutrition tracking drop-off and macro gaps."""
        logged_7d = sum(1 for s in recent_7 if s.nutrition_logged)
        total_7d = len(recent_7)

        if total_7d == 0:
            return

        # Compare to prior week
        logged_28d = sum(1 for s in recent_28 if s.nutrition_logged)
        total_28d = len(recent_28)

        week_pct = (logged_7d / total_7d) * 100 if total_7d else 0
        month_pct = (logged_28d / total_28d) * 100 if total_28d else 0

        if week_pct >= 85:
            strengths.append(f"Excellent nutrition tracking ({logged_7d}/{total_7d} days)")
            trends["nutrition"] = "stable"
        elif week_pct < month_pct - 15:
            risk_flags.append({
                "domain": "nutrition",
                "severity": "info",
                "message": f"Nutrition logging declined ({week_pct:.0f}% this week vs {month_pct:.0f}% monthly avg)",
            })
            trends["nutrition"] = "declining"
        elif week_pct < 50:
            weaknesses.append(f"Low nutrition tracking ({logged_7d}/{total_7d} days this week)")
            trends["nutrition"] = "declining"
        else:
            trends["nutrition"] = "stable"

        # Protein adequacy check
        protein_days = [s for s in recent_7 if s.protein_g and s.weight]
        if protein_days:
            avg_protein = sum(float(s.protein_g) for s in protein_days) / len(protein_days)
            avg_weight = sum(float(s.weight) for s in protein_days) / len(protein_days)
            if avg_weight > 0:
                ratio = avg_protein / avg_weight
                if ratio < 0.6:
                    risk_flags.append({
                        "domain": "nutrition",
                        "severity": "warning",
                        "message": f"Low protein intake ({avg_protein:.0f}g/day, {ratio:.2f}g/lb body weight)",
                    })
                elif ratio >= 0.8:
                    strengths.append(f"Strong protein intake ({avg_protein:.0f}g/day)")

    @staticmethod
    def _detect_workout_patterns(recent_7, recent_28, strengths, weaknesses,
                                  risk_flags, trends):
        """Detect workout frequency trends."""
        workouts_7d = sum(1 for s in recent_7 if s.workout_count > 0)
        workouts_28d = sum(1 for s in recent_28 if s.workout_count > 0)

        if len(recent_28) == 0:
            return

        weekly_avg = workouts_28d / max(1, len(recent_28) / 7)

        if workouts_7d >= 4:
            strengths.append(f"Strong workout frequency ({workouts_7d} this week)")
            trends["workout"] = "strong"
        elif workouts_7d >= 3:
            trends["workout"] = "stable"
        elif workouts_7d < weekly_avg * 0.6 and weekly_avg > 2:
            risk_flags.append({
                "domain": "workout",
                "severity": "info",
                "message": f"Workout frequency dropped ({workouts_7d} this week vs {weekly_avg:.1f} avg)",
            })
            trends["workout"] = "declining"
        elif workouts_7d <= 1:
            weaknesses.append(f"Low workout frequency ({workouts_7d} this week)")
            trends["workout"] = "declining"
        else:
            trends["workout"] = "stable"

        # Volume trend (check training_load over weeks)
        load_days = [s for s in recent_28 if s.training_load]
        if len(load_days) >= 14:
            first_half = load_days[:len(load_days)//2]
            second_half = load_days[len(load_days)//2:]
            avg_first = sum(float(s.training_load) for s in first_half) / len(first_half)
            avg_second = sum(float(s.training_load) for s in second_half) / len(second_half)
            if avg_first > 0:
                change_pct = ((avg_second - avg_first) / avg_first) * 100
                if change_pct >= 5:
                    strengths.append(f"Progressive overload: training volume up {change_pct:.0f}%")
                elif change_pct <= -15:
                    weaknesses.append(f"Training volume declining ({change_pct:.0f}%)")

    @staticmethod
    def _detect_glucose_patterns(recent_7, recent_28, prior_28,
                                  strengths, weaknesses, risk_flags, trends):
        """Detect glucose trends and variability patterns."""
        glucose_7d = [s for s in recent_7 if s.glucose_avg is not None]
        glucose_28d = [s for s in recent_28 if s.glucose_avg is not None]
        glucose_prior = [s for s in prior_28 if s.glucose_avg is not None]

        if not glucose_7d:
            return

        avg_7d = sum(float(s.glucose_avg) for s in glucose_7d) / len(glucose_7d)

        # Time in range
        tir_days = [s for s in glucose_7d if s.time_in_range_pct is not None]
        if tir_days:
            avg_tir = sum(float(s.time_in_range_pct) for s in tir_days) / len(tir_days)
            if avg_tir >= 85:
                strengths.append(f"Excellent glucose control ({avg_tir:.0f}% time in range)")
            elif avg_tir < 60:
                weaknesses.append(f"Low time in range ({avg_tir:.0f}%, target: >70%)")

        # Worsening trend (compare 28d vs prior 28d)
        if glucose_28d and glucose_prior:
            avg_28d = sum(float(s.glucose_avg) for s in glucose_28d) / len(glucose_28d)
            avg_prior = sum(float(s.glucose_avg) for s in glucose_prior) / len(glucose_prior)
            change = avg_28d - avg_prior

            if change > 5:
                risk_flags.append({
                    "domain": "glucose",
                    "severity": "warning",
                    "message": f"Average glucose rising: {avg_prior:.0f} → {avg_28d:.0f} mg/dL",
                })
                trends["glucose"] = "worsening"
            elif change < -5:
                strengths.append(f"Glucose improving: {avg_prior:.0f} → {avg_28d:.0f} mg/dL")
                trends["glucose"] = "improving"
            else:
                trends["glucose"] = "stable"
        else:
            trends["glucose"] = "stable"

    @staticmethod
    def _detect_activity_patterns(recent_7, recent_28, strengths, weaknesses,
                                   risk_flags, trends):
        """Detect step and activity trends."""
        step_days_7 = [s for s in recent_7 if s.steps is not None]
        step_days_28 = [s for s in recent_28 if s.steps is not None]

        if not step_days_7:
            return

        avg_7d = sum(s.steps for s in step_days_7) / len(step_days_7)

        if avg_7d >= 10000:
            strengths.append(f"Strong activity level ({avg_7d:,.0f} avg steps)")
            trends["activity"] = "strong"
        elif avg_7d < 5000:
            weaknesses.append(f"Low daily activity ({avg_7d:,.0f} avg steps)")
            trends["activity"] = "low"
        else:
            trends["activity"] = "moderate"

        # Declining trend
        if step_days_28 and len(step_days_28) >= 14:
            first_half = step_days_28[:len(step_days_28)//2]
            second_half = step_days_28[len(step_days_28)//2:]
            avg_first = sum(s.steps for s in first_half) / len(first_half)
            avg_second = sum(s.steps for s in second_half) / len(second_half)
            if avg_first > 0 and ((avg_second - avg_first) / avg_first) < -0.15:
                risk_flags.append({
                    "domain": "activity",
                    "severity": "info",
                    "message": f"Daily steps declining ({avg_first:,.0f} → {avg_second:,.0f})",
                })

    @staticmethod
    def _detect_medication_patterns(recent_7, recent_28, strengths, weaknesses,
                                     risk_flags, trends):
        """Detect medication adherence patterns."""
        med_days_7 = [s for s in recent_7 if s.medication_adherence_pct is not None]
        if not med_days_7:
            return

        avg_adherence = sum(float(s.medication_adherence_pct) for s in med_days_7) / len(med_days_7)

        if avg_adherence >= 90:
            strengths.append(f"Excellent medication adherence ({avg_adherence:.0f}%)")
            trends["medication"] = "strong"
        elif avg_adherence < 70:
            risk_flags.append({
                "domain": "medication",
                "severity": "warning",
                "message": f"Low medication adherence ({avg_adherence:.0f}%)",
            })
            trends["medication"] = "declining"
        else:
            trends["medication"] = "stable"

    @staticmethod
    def _detect_protein_patterns(recent_7, recent_28, user, target_date,
                                  strengths, weaknesses, risk_flags, trends):
        """
        Detect protein intake patterns, workout-day adequacy, and consistency.

        Uses LBM-aware targets when available; falls back to body weight method.
        """
        from apps.health.services.protein_service import ProteinService

        protein_7d = [s for s in recent_7 if s.protein_g is not None]
        protein_28d = [s for s in recent_28 if s.protein_g is not None]

        if not protein_7d:
            return

        avg_protein_7d = sum(float(s.protein_g) for s in protein_7d) / len(protein_7d)

        # Calculate target for context (returns dict with target_g, method, lbm)
        target_info = ProteinService.calculate_target(user, target_date)
        target = float(target_info["target_g"]) if target_info else None
        method = target_info["method"] if target_info else None

        method_note = ""
        if method == "lean_body_mass" and target_info.get("lbm"):
            method_note = f" [LBM: {target_info['lbm']:.0f} lbs]"

        if target:
            avg_ratio = avg_protein_7d / target if target > 0 else 0

            if avg_ratio >= 0.9:
                strengths.append(
                    f"Strong protein intake ({avg_protein_7d:.0f}g/day, {avg_ratio:.0%} of target{method_note})"
                )
                trends["protein"] = "strong"
            elif avg_ratio >= 0.7:
                trends["protein"] = "adequate"
            elif avg_ratio >= 0.5:
                weaknesses.append(
                    f"Below protein target ({avg_protein_7d:.0f}g/day, {avg_ratio:.0%} of {target:.0f}g{method_note})"
                )
                trends["protein"] = "low"
            else:
                risk_flags.append({
                    "domain": "protein",
                    "severity": "warning",
                    "message": (
                        f"Very low protein intake ({avg_protein_7d:.0f}g/day, "
                        f"{avg_ratio:.0%} of {target:.0f}g target{method_note})"
                    ),
                })
                trends["protein"] = "critically_low"
        else:
            # No target available — report raw values
            weight_days = [s for s in protein_7d if s.weight]
            if weight_days:
                avg_weight = sum(float(s.weight) for s in weight_days) / len(weight_days)
                per_lb = avg_protein_7d / avg_weight if avg_weight > 0 else 0
                if per_lb < 0.5:
                    weaknesses.append(
                        f"Low protein ({avg_protein_7d:.0f}g/day, {per_lb:.2f}g/lb)"
                    )
                    trends["protein"] = "low"
                elif per_lb >= 0.7:
                    strengths.append(
                        f"Good protein intake ({avg_protein_7d:.0f}g/day, {per_lb:.2f}g/lb)"
                    )
                    trends["protein"] = "strong"
                else:
                    trends["protein"] = "adequate"

        # Workout-day protein check — LBM-aware
        # On workout days, target is LBM × 1.1 (higher), so undershoot is worse
        workout_protein_7d = [
            s for s in recent_7
            if s.workout_count and s.workout_count > 0 and s.protein_g is not None
        ]
        if workout_protein_7d and target:
            workout_avg = sum(float(s.protein_g) for s in workout_protein_7d) / len(workout_protein_7d)

            # For workout-day comparison, get workout-day target if LBM method
            workout_target = target
            if target_info and target_info["method"] == "lean_body_mass" and target_info.get("lbm"):
                from apps.health.services.protein_service import LBM_WORKOUT_MULTIPLIER
                workout_target = target_info["lbm"] * float(LBM_WORKOUT_MULTIPLIER)

            workout_ratio = workout_avg / workout_target if workout_target > 0 else 0
            if workout_ratio < 0.85:
                risk_flags.append({
                    "domain": "protein",
                    "severity": "warning",
                    "message": (
                        f"Low protein on training days ({workout_avg:.0f}g avg, "
                        f"{workout_ratio:.0%} of {workout_target:.0f}g target) — may impair recovery"
                    ),
                })

        # Rest vs workout day protein gap
        rest_protein_7d = [
            s for s in recent_7
            if (not s.workout_count or s.workout_count == 0) and s.protein_g is not None
        ]
        if workout_protein_7d and rest_protein_7d:
            workout_avg = sum(float(s.protein_g) for s in workout_protein_7d) / len(workout_protein_7d)
            rest_avg = sum(float(s.protein_g) for s in rest_protein_7d) / len(rest_protein_7d)
            if rest_avg > 0 and workout_avg < rest_avg * 0.9:
                # Protein should be HIGHER on workout days, not lower
                risk_flags.append({
                    "domain": "protein",
                    "severity": "info",
                    "message": (
                        f"Protein lower on training days ({workout_avg:.0f}g) than rest days "
                        f"({rest_avg:.0f}g) — should be higher for recovery"
                    ),
                })

        # Protein consistency trend (28d vs first 28d)
        if len(protein_28d) >= 14:
            first_half = protein_28d[:len(protein_28d)//2]
            second_half = protein_28d[len(protein_28d)//2:]
            avg_first = sum(float(s.protein_g) for s in first_half) / len(first_half)
            avg_second = sum(float(s.protein_g) for s in second_half) / len(second_half)
            if avg_first > 0:
                change_pct = ((avg_second - avg_first) / avg_first) * 100
                if change_pct >= 10:
                    strengths.append(
                        f"Protein intake improving (+{change_pct:.0f}% over 2 weeks)"
                    )
                elif change_pct <= -15:
                    weaknesses.append(
                        f"Protein intake declining ({change_pct:.0f}% over 2 weeks)"
                    )

    @staticmethod
    def _determine_top_recommendation(risk_flags, weaknesses, strengths):
        """Pick the single most impactful recommendation."""
        # Priority: warning risk flags > info risk flags > weaknesses
        warnings = [r for r in risk_flags if r.get("severity") == "warning"]
        if warnings:
            return warnings[0]["message"]

        infos = [r for r in risk_flags if r.get("severity") == "info"]
        if infos:
            return infos[0]["message"]

        if weaknesses:
            return weaknesses[0]

        if strengths:
            return f"Keep it up — {strengths[0].lower()}"

        return "Tracking consistently — keep logging to build trend data"
