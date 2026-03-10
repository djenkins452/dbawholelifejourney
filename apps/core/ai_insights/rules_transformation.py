"""
Transformation Insight Rules — Cross-module rules for body transformation tracking.

Rules:
- NutritionCalorieTrendRule: Detect calorie intake trending away from target
- ProteinDeficitRule: Detect sustained protein under-intake
- CarbGlucoseCorrelationRule: Detect high carbs correlating with high glucose
- FastingConsistencyRule: Detect fasting consistency changes
- WorkoutConsistencyRule: Detect workout frequency changes
- StrengthPlateauRule: Detect strength plateaus
- TransformationMomentumRule: Detect overall transformation momentum changes
"""

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import (
    days_since,
    get_time_window,
)
from apps.core.ai_insights.rule_registry import register

MEDICAL_DISCLAIMER = (
    "\n\n_Educational information only — not medical advice. "
    "Please consult your healthcare provider for medical guidance._"
)


@register
class NutritionCalorieTrendRule(BaseInsightRule):
    """Detect when calorie intake is consistently off target."""

    rule_name = "nutrition_calorie_trend"
    module = "health"
    insight_type = "nutrition_calorie_trend"

    def applies(self, user, event):
        module = event.get("module", "")
        action = event.get("action", "")
        return module in ("health", "nutrition") or event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        # Try SAE state first
        user_state = event.get("user_state", {})
        nutrition = user_state.get("nutrition", {})

        rolling_cal = nutrition.get("rolling_7d_calories_avg")
        target = nutrition.get("calorie_target")

        if rolling_cal is None or target is None or target <= 0:
            return []

        deviation_pct = abs(rolling_cal - target) / target * 100
        if deviation_pct < 20:
            return []  # Within acceptable range

        window_start, window_end = get_time_window(days=7)
        over_under = "over" if rolling_cal > target else "under"
        severity = "warning" if over_under == "over" else "info"

        return [
            {
                "severity": severity,
                "title": f"Calories {over_under} target by {deviation_pct:.0f}%",
                "message": (
                    f"Your 7-day average calorie intake is {rolling_cal:.0f} kcal, "
                    f"which is {deviation_pct:.0f}% {over_under} your target of {target} kcal. "
                    f"Consistent {'overeating' if over_under == 'over' else 'undereating'} "
                    f"can impact your transformation progress."
                    f"{MEDICAL_DISCLAIMER}"
                ),
                "confidence_score": 0.80,
                "explain_why": (
                    f"Rule: {self.rule_name}. 7-day avg: {rolling_cal:.0f} kcal, "
                    f"target: {target} kcal, deviation: {deviation_pct:.0f}% (threshold: 20%)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "rolling_7d_avg": rolling_cal,
                    "target": target,
                    "deviation_pct": round(deviation_pct, 1),
                    "direction": over_under,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]


@register
class ProteinDeficitRule(BaseInsightRule):
    """Detect sustained protein under-intake relative to target."""

    rule_name = "protein_deficit"
    module = "health"
    insight_type = "protein_deficit"

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("health", "nutrition") or event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        user_state = event.get("user_state", {})
        nutrition = user_state.get("nutrition", {})

        rolling_protein = nutrition.get("rolling_7d_protein_avg")
        target = nutrition.get("protein_target")

        if rolling_protein is None or target is None or target <= 0:
            return []

        compliance_pct = rolling_protein / target * 100
        if compliance_pct >= 80:
            return []  # Adequate protein intake

        deficit_g = target - rolling_protein
        window_start, window_end = get_time_window(days=7)

        return [
            {
                "severity": "warning",
                "title": f"Protein intake {compliance_pct:.0f}% of target",
                "message": (
                    f"Your 7-day average protein intake is {rolling_protein:.0f}g, "
                    f"which is {deficit_g:.0f}g below your target of {target:.0f}g per day. "
                    f"Adequate protein is essential for muscle preservation and recovery."
                    f"{MEDICAL_DISCLAIMER}"
                ),
                "confidence_score": 0.82,
                "explain_why": (
                    f"Rule: {self.rule_name}. 7-day avg protein: {rolling_protein:.0f}g, "
                    f"target: {target:.0f}g, compliance: {compliance_pct:.0f}% (threshold: 80%)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "rolling_7d_protein_avg": rolling_protein,
                    "protein_target": target,
                    "compliance_pct": round(compliance_pct, 1),
                    "deficit_g": round(deficit_g, 1),
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]


@register
class CarbGlucoseCorrelationRule(BaseInsightRule):
    """Detect correlation between high carb intake and elevated glucose."""

    rule_name = "carb_glucose_correlation"
    module = "health"
    insight_type = "carb_glucose_correlation"

    def applies(self, user, event):
        return event.get("module") in ("health", "nutrition") or event.get(
            "event_type"
        ) == "scheduled_check"

    def evaluate(self, user, event):
        user_state = event.get("user_state", {})
        nutrition = user_state.get("nutrition", {})
        health = user_state.get("health", {})

        daily_carbs = nutrition.get("daily_carbs_g")
        carb_target = nutrition.get("carb_target")

        if daily_carbs is None or carb_target is None or carb_target <= 0:
            return []

        # Check if carbs significantly over target
        carb_ratio = daily_carbs / carb_target
        if carb_ratio < 1.3:
            return []

        # Check glucose data — look for recent high readings
        from apps.health.models import GlucoseEntry
        from apps.core.time.system_clock import get_current_time

        now = get_current_time()
        from datetime import timedelta

        recent_glucose = (
            GlucoseEntry.objects.filter(
                user=user,
                recorded_at__gte=now - timedelta(days=1),
                status="active",
            )
            .order_by("-recorded_at")
            .values_list("id", "value", "recorded_at")[:5]
        )

        high_readings = [g for g in recent_glucose if float(g[1]) > 140]
        if not high_readings:
            return []

        window_start, window_end = get_time_window(days=1)
        record_ids = [g[0] for g in high_readings]

        return [
            {
                "severity": "info",
                "title": "High carbs may be driving glucose spikes",
                "message": (
                    f"Today's carb intake ({daily_carbs:.0f}g) is {carb_ratio:.0f}x your target "
                    f"({carb_target:.0f}g), and you had {len(high_readings)} glucose reading(s) "
                    f"above 140 mg/dL. Consider spacing out carb-heavy meals or choosing "
                    f"lower-glycemic options."
                    f"{MEDICAL_DISCLAIMER}"
                ),
                "confidence_score": 0.70,
                "explain_why": (
                    f"Rule: {self.rule_name}. Daily carbs: {daily_carbs:.0f}g "
                    f"(target: {carb_target:.0f}g, ratio: {carb_ratio:.1f}x). "
                    f"High glucose readings: {len(high_readings)}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "daily_carbs_g": daily_carbs,
                    "carb_target": carb_target,
                    "carb_ratio": round(carb_ratio, 1),
                    "high_glucose_count": len(high_readings),
                    "record_ids": record_ids,
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                    record_ids,
                ),
            }
        ]


@register
class FastingConsistencyRule(BaseInsightRule):
    """Detect changes in fasting consistency."""

    rule_name = "fasting_consistency"
    module = "health"
    insight_type = "fasting_consistency"

    def applies(self, user, event):
        module = event.get("module", "")
        action = event.get("action", "")
        return module == "health" and action in (
            "end_fast",
            "start_fast",
            "scheduled_check",
        ) or event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        user_state = event.get("user_state", {})
        fasting = user_state.get("fasting", {})

        fasts_7d = fasting.get("fasts_7d", 0)
        compliance = fasting.get("fasting_compliance_score")

        if fasts_7d == 0 and compliance is None:
            return []  # User doesn't fast

        window_start, window_end = get_time_window(days=7)

        # Check for high compliance
        if compliance is not None and compliance >= 80:
            return [
                {
                    "severity": "positive",
                    "title": f"Great fasting consistency ({compliance:.0f}%)",
                    "message": (
                        f"You completed {fasts_7d} fast(s) this week with a "
                        f"compliance score of {compliance:.0f}%. Keep it up!"
                    ),
                    "confidence_score": 0.80,
                    "explain_why": (
                        f"Rule: {self.rule_name}. 7-day fasts: {fasts_7d}, "
                        f"compliance: {compliance:.0f}% (threshold: 80%)."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "fasts_7d": fasts_7d,
                        "compliance_score": compliance,
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type + "_positive",
                        window_start.date(),
                        window_end.date(),
                    ),
                }
            ]

        # Low consistency warning (only if they've fasted before)
        if fasts_7d == 0:
            last_end = fasting.get("last_fast_end")
            if last_end:
                return [
                    {
                        "severity": "info",
                        "title": "No fasts this week",
                        "message": (
                            "You didn't complete any fasting windows this week. "
                            "If intermittent fasting is part of your protocol, "
                            "consider getting back on track."
                        ),
                        "confidence_score": 0.70,
                        "explain_why": (
                            f"Rule: {self.rule_name}. 0 fasts in 7 days, "
                            f"but user has prior fasting history."
                        ),
                        "evidence": {
                            "rule_name": self.rule_name,
                            "fasts_7d": 0,
                            "last_fast_end": last_end,
                        },
                        "dedupe_key": build_dedupe_key(
                            user.id,
                            self.insight_type + "_missing",
                            window_start.date(),
                            window_end.date(),
                        ),
                    }
                ]

        return []


@register
class WorkoutConsistencyRule(BaseInsightRule):
    """Detect workout frequency changes."""

    rule_name = "workout_consistency"
    module = "health"
    insight_type = "workout_consistency"

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("health", "fitness") or event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        user_state = event.get("user_state", {})
        fitness = user_state.get("fitness", {})

        workouts_7d = fitness.get("workouts_7d", 0)
        workouts_30d = fitness.get("workouts_30d", 0)
        consistency = fitness.get("workout_consistency_score")

        if workouts_30d == 0:
            return []  # No workout history

        window_start, window_end = get_time_window(days=7)
        weekly_avg = workouts_30d / 4.0

        # Positive: consistency above 100%
        if consistency is not None and consistency >= 100 and workouts_7d >= 3:
            return [
                {
                    "severity": "positive",
                    "title": f"Strong workout week ({workouts_7d} sessions)",
                    "message": (
                        f"You completed {workouts_7d} workout(s) this week, meeting or "
                        f"exceeding your average of {weekly_avg:.1f}/week. Great consistency!"
                    ),
                    "confidence_score": 0.85,
                    "explain_why": (
                        f"Rule: {self.rule_name}. 7-day workouts: {workouts_7d}, "
                        f"30-day avg: {weekly_avg:.1f}/week, consistency: {consistency:.0f}%."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "workouts_7d": workouts_7d,
                        "workouts_30d": workouts_30d,
                        "weekly_avg": round(weekly_avg, 1),
                        "consistency_score": consistency,
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type + "_positive",
                        window_start.date(),
                        window_end.date(),
                    ),
                }
            ]

        # Warning: workout frequency dropped significantly
        if weekly_avg >= 2 and workouts_7d == 0:
            return [
                {
                    "severity": "warning",
                    "title": "No workouts this week",
                    "message": (
                        f"You haven't logged any workouts this week. Your 30-day average "
                        f"is {weekly_avg:.1f} workouts/week. A rest week can be beneficial, "
                        f"but consistent training drives transformation results."
                    ),
                    "confidence_score": 0.80,
                    "explain_why": (
                        f"Rule: {self.rule_name}. 0 workouts in 7 days, "
                        f"30-day avg: {weekly_avg:.1f}/week."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "workouts_7d": 0,
                        "workouts_30d": workouts_30d,
                        "weekly_avg": round(weekly_avg, 1),
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type + "_drop",
                        window_start.date(),
                        window_end.date(),
                    ),
                }
            ]

        return []


@register
class StrengthPlateauRule(BaseInsightRule):
    """Detect exercise-specific strength plateaus.

    Uses per-exercise progress data from the SAE fitness state to identify
    which specific exercises are plateauing, improving, or regressing.
    Produces coach-like insights that name the specific exercises involved.

    Falls back to global plateau detection if exercise_progress is unavailable.
    """

    rule_name = "strength_plateau"
    module = "health"
    insight_type = "strength_plateau"

    def applies(self, user, event):
        return event.get("module") in ("health", "fitness") or event.get(
            "event_type"
        ) == "scheduled_check"

    def evaluate(self, user, event):
        user_state = event.get("user_state", {})
        fitness = user_state.get("fitness", {})
        workouts_30d = fitness.get("workouts_30d", 0)

        # Must be training consistently
        if workouts_30d < 8:
            return []

        exercise_progress = fitness.get("exercise_progress")
        if exercise_progress is not None:
            return self._evaluate_per_exercise(user, fitness, exercise_progress)
        return self._evaluate_global_fallback(user, fitness)

    def _evaluate_per_exercise(self, user, fitness, exercise_progress):
        """Exercise-specific plateau detection."""
        plateauing = [e for e in exercise_progress if e["status"] == "plateau"]
        improving = [e for e in exercise_progress if e["status"] == "improving"]
        regressing = [e for e in exercise_progress if e["status"] == "regressing"]

        if not plateauing and not regressing:
            # No plateau or regression — resolve any stale plateau insights
            self._resolve_stale_insights(user)
            return []

        window_start, window_end = get_time_window(days=30)

        # Build exercise-specific message
        stalled = plateauing + regressing
        stalled_names = [e["exercise"].lower() for e in stalled]
        improving_names = [e["exercise"].lower() for e in improving]

        message = self._build_message(stalled, improving, stalled_names, improving_names)

        return [
            {
                "severity": "info",
                "title": "Exercise plateau detected",
                "message": message,
                "confidence_score": 0.75,
                "explain_why": (
                    f"Rule: {self.rule_name}. "
                    f"Plateauing: {', '.join(e['exercise'] for e in plateauing) or 'none'}. "
                    f"Regressing: {', '.join(e['exercise'] for e in regressing) or 'none'}. "
                    f"Improving: {', '.join(e['exercise'] for e in improving) or 'none'}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "exercise_progress": exercise_progress,
                    "plateauing": [e["exercise"] for e in plateauing],
                    "improving": [e["exercise"] for e in improving],
                    "regressing": [e["exercise"] for e in regressing],
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]

    @staticmethod
    def _build_message(stalled, improving, stalled_names, improving_names):
        """Build a coach-like message naming specific exercises."""
        # Format stalled exercise names
        if len(stalled_names) == 1:
            stalled_str = f"your {stalled_names[0]}"
        elif len(stalled_names) == 2:
            stalled_str = f"your {stalled_names[0]} and {stalled_names[1]}"
        else:
            stalled_str = (
                "your " + ", ".join(stalled_names[:-1]) + f", and {stalled_names[-1]}"
            )

        # Classify stalled exercises
        plateau_names = [e["exercise"].lower() for e in stalled if e["status"] == "plateau"]
        regressing_names = [e["exercise"].lower() for e in stalled if e["status"] == "regressing"]

        if plateau_names and regressing_names:
            verb = "appears stalled"
            if len(regressing_names) == 1:
                detail = f", and your {regressing_names[0]} volume is declining"
            else:
                detail = ", with some exercises also declining in volume"
        elif regressing_names:
            verb = "has been declining"
            detail = ""
        else:
            verb = "appears to be plateauing" if len(stalled) == 1 else "appear to be plateauing"
            detail = ""

        msg = f"{stalled_str.capitalize()} {verb}{detail}."

        if improving_names:
            if len(improving_names) == 1:
                msg += f" However, your {improving_names[0]} is still progressing."
            elif len(improving_names) == 2:
                msg += (
                    f" However, your {improving_names[0]} and "
                    f"{improving_names[1]} are still progressing."
                )
            else:
                msg += (
                    f" However, {len(improving_names)} other exercises "
                    f"are still progressing."
                )

        msg += (
            " Consider adjusting your programming for the stalled lifts "
            "— progressive overload, deload weeks, or exercise variations "
            "may help break through."
        )
        return msg

    def _resolve_stale_insights(self, user):
        """Dismiss active plateau insights when condition no longer holds.

        Called when the StrengthPlateauRule evaluates and finds NO
        plateauing or regressing exercises.  Without this, old plateau
        insights remain with status="new"/"read" indefinitely because
        the rule returns [] and no counterpart insight is generated.
        """
        import logging

        from apps.core.ai_insights.models import Insight

        _logger = logging.getLogger(__name__)
        updated = Insight.objects.filter(
            user=user,
            insight_type=self.insight_type,
            status__in=["new", "read"],
        ).update(status="dismissed")
        if updated:
            _logger.info(
                "PLATEAU_RESOLVED user=%s dismissed=%d — exercises no longer "
                "plateauing/regressing",
                user.id,
                updated,
            )

    def _evaluate_global_fallback(self, user, fitness):
        """Fallback: global plateau detection for legacy cached state."""
        prs_30d = fitness.get("prs_30d", 0)
        workouts_30d = fitness.get("workouts_30d", 0)
        strength_trend = fitness.get("strength_trend_score", "insufficient_data")

        if prs_30d > 0:
            self._resolve_stale_insights(user)
            return []
        if strength_trend == "increasing":
            self._resolve_stale_insights(user)
            return []

        window_start, window_end = get_time_window(days=30)

        return [
            {
                "severity": "info",
                "title": "Strength plateau detected",
                "message": (
                    f"You've completed {workouts_30d} workouts in the last 30 days "
                    f"without setting any personal records. "
                    f"Consider adjusting your programming — progressive overload, "
                    f"deload weeks, or exercise variations may help break through."
                ),
                "confidence_score": 0.72,
                "explain_why": (
                    f"Rule: {self.rule_name}. 30-day workouts: {workouts_30d}, "
                    f"30-day PRs: 0, strength trend: {strength_trend}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "workouts_30d": workouts_30d,
                    "prs_30d": 0,
                    "strength_trend": strength_trend,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]


@register
class TransformationMomentumRule(BaseInsightRule):
    """Detect overall transformation momentum changes."""

    rule_name = "transformation_momentum"
    module = "health"
    insight_type = "transformation_momentum"

    def applies(self, user, event):
        return event.get("module") in ("all", "health", "nutrition", "fitness") or event.get(
            "event_type"
        ) == "scheduled_check"

    def evaluate(self, user, event):
        user_state = event.get("user_state", {})
        transformation = user_state.get("transformation", {})

        score = transformation.get("transformation_score")
        momentum = transformation.get("momentum_score")

        if score is None:
            return []

        window_start, window_end = get_time_window(days=7)

        # High momentum — celebrate
        if score >= 70:
            return [
                {
                    "severity": "positive",
                    "title": f"Transformation on track (score: {score})",
                    "message": (
                        f"Your overall transformation score is {score}/100. "
                        f"You're maintaining strong consistency across nutrition, "
                        f"training, and recovery. Keep this momentum going!"
                    ),
                    "confidence_score": 0.85,
                    "explain_why": (
                        f"Rule: {self.rule_name}. Transformation score: {score} "
                        f"(threshold: 70). Momentum: {momentum}."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "transformation_score": score,
                        "momentum_score": momentum,
                        "sub_scores": {
                            k: transformation.get(k)
                            for k in (
                                "weight_trend_score",
                                "nutrition_score",
                                "workout_score",
                                "fasting_score",
                                "recovery_score",
                            )
                            if transformation.get(k) is not None
                        },
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type + "_positive",
                        window_start.date(),
                        window_end.date(),
                    ),
                }
            ]

        # Low momentum — nudge
        if score < 40 and momentum is not None and momentum < 60:
            return [
                {
                    "severity": "warning",
                    "title": f"Transformation momentum dropping (score: {score})",
                    "message": (
                        f"Your transformation score has dropped to {score}/100 "
                        f"with a momentum score of {momentum}/100. Focus on the "
                        f"basics: hit your protein target, get your workouts in, "
                        f"and maintain your sleep schedule."
                    ),
                    "confidence_score": 0.75,
                    "explain_why": (
                        f"Rule: {self.rule_name}. Transformation score: {score} "
                        f"(threshold: <40), momentum: {momentum} (threshold: <60)."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "transformation_score": score,
                        "momentum_score": momentum,
                        "sub_scores": {
                            k: transformation.get(k)
                            for k in (
                                "weight_trend_score",
                                "nutrition_score",
                                "workout_score",
                                "fasting_score",
                                "recovery_score",
                            )
                            if transformation.get(k) is not None
                        },
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type + "_warning",
                        window_start.date(),
                        window_end.date(),
                    ),
                }
            ]

        return []
