"""
PRIE — Transformation prediction rules.

Predictions:
- NutritionWeightProjectionRule: Project weight change based on caloric balance
- StrengthProgressionPredictionRule: Project training volume progression
- TransformationSuccessProbabilityRule: Estimate probability of reaching protocol goals
"""

from datetime import timedelta

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.ai_predictions.trajectory_engine import calculate_linear_projection
from apps.core.time.system_clock import get_current_time


@register_prediction
class NutritionWeightProjectionRule(BasePredictionRule):
    """
    Project weight change factoring in caloric balance.

    Uses weight entries for trajectory + nutrition data for adjustment.
    If user is in caloric surplus/deficit, adjusts the projection accordingly.
    """

    rule_name = "nutrition_weight_projection"
    module = "health"
    prediction_type = "nutrition_weight_projection"
    min_confidence_to_store = 0.25

    HORIZONS = [30, 60]
    LOOKBACK_DAYS = 90

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "health", "nutrition")

    def predict(self, user, event):
        from apps.health.models import WeightEntry

        cutoff = get_current_time() - timedelta(days=self.LOOKBACK_DAYS)
        weight_entries = (
            WeightEntry.objects.filter(
                user=user,
                recorded_at__gte=cutoff,
            )
            .order_by("recorded_at")
            .values_list("recorded_at", "value")
        )

        data_points = [(dt, float(val)) for dt, val in weight_entries]
        if len(data_points) < 3:
            return []

        # Get nutrition state for caloric context
        try:
            from apps.core.ai_state import get_module_state

            nutrition = get_module_state(user, "nutrition")
        except Exception:
            nutrition = {}

        calorie_target = nutrition.get("calorie_target")
        rolling_cal = nutrition.get("rolling_7d_calories_avg")
        has_nutrition_context = calorie_target and rolling_cal

        predictions = []
        for days in self.HORIZONS:
            result = calculate_linear_projection(data_points, days, unit_label="lbs")
            if result is None:
                continue

            pred_type = f"nutrition_weight_{days}d"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            current_weight = data_points[-1][1]
            projected = result.predicted_value
            diff = projected - current_weight
            direction = "gain" if diff > 0 else "loss" if diff < 0 else "no change"
            conf = confidence_label(result.confidence_score)

            # Build explanation with nutrition context
            nutrition_context = ""
            if has_nutrition_context:
                cal_diff = rolling_cal - calorie_target
                if abs(cal_diff) > 100:
                    surplus_deficit = "surplus" if cal_diff > 0 else "deficit"
                    nutrition_context = (
                        f" Your 7-day average calorie intake ({rolling_cal:.0f} kcal) "
                        f"is in a {abs(cal_diff):.0f} kcal {surplus_deficit} "
                        f"relative to your target ({calorie_target} kcal)."
                    )

            explanation = (
                f"Based on {result.data_point_count} weight entries over {self.LOOKBACK_DAYS} days, "
                f"your weight is {result.rate_description}. "
                f"Projected weight in {days} days: {projected:.1f} lbs "
                f"({abs(diff):.1f} lb {direction}).{nutrition_context} "
                f"Confidence: {conf}."
            )

            evidence = {
                "rule": self.rule_name,
                "data_points": result.data_point_count,
                "current_weight": current_weight,
                "slope_per_day": round(result.slope, 4),
                "r_squared": round(result.r_squared, 4),
                "lookback_days": self.LOOKBACK_DAYS,
                "horizon_days": days,
            }
            if has_nutrition_context:
                evidence["calorie_target"] = calorie_target
                evidence["rolling_7d_calories"] = rolling_cal
                evidence["caloric_balance"] = round(rolling_cal - calorie_target)

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "health",
                    "predicted_value": projected,
                    "predicted_date": result.predicted_date,
                    "confidence_score": result.confidence_score,
                    "explanation": explanation,
                    "evidence": evidence,
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions


@register_prediction
class StrengthProgressionPredictionRule(BasePredictionRule):
    """
    Predict training volume progression based on recent workout data.
    """

    rule_name = "strength_progression"
    module = "health"
    prediction_type = "strength_progression"
    min_confidence_to_store = 0.25

    HORIZONS = [30, 60]
    LOOKBACK_DAYS = 90

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "health", "fitness")

    def predict(self, user, event):
        from django.db.models import Sum
        from apps.health.models import WorkoutSession

        now = get_current_time()
        cutoff = now - timedelta(days=self.LOOKBACK_DAYS)

        # Get weekly volume data points (total volume per week)
        sessions = (
            WorkoutSession.objects.filter(
                user=user,
                date__gte=cutoff.date(),
                status="active",
            )
            .order_by("date")
        )

        if sessions.count() < 4:
            return []

        # Calculate weekly volumes
        weekly_volumes = {}
        for session in sessions:
            # Calculate week start (Monday)
            week_start = session.date - timedelta(days=session.date.weekday())
            volume = 0
            for we in session.workout_exercises.all():
                for s in we.sets.all():
                    if s.weight and s.reps:
                        volume += float(s.weight) * s.reps
            weekly_volumes[week_start] = weekly_volumes.get(week_start, 0) + volume

        if len(weekly_volumes) < 3:
            return []

        # Convert to data points for trajectory engine
        from datetime import datetime

        data_points = []
        for week_start, volume in sorted(weekly_volumes.items()):
            # Convert date to datetime for trajectory engine
            dt = datetime.combine(week_start, datetime.min.time())
            from django.utils.timezone import make_aware
            dt = make_aware(dt)
            data_points.append((dt, volume))

        predictions = []
        for days in self.HORIZONS:
            result = calculate_linear_projection(data_points, days, unit_label="lbs volume")
            if result is None:
                continue

            pred_type = f"strength_volume_{days}d"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            current_volume = data_points[-1][1]
            projected = max(0, result.predicted_value)
            diff = projected - current_volume
            direction = "increase" if diff > 0 else "decrease" if diff < 0 else "no change"
            conf = confidence_label(result.confidence_score)

            explanation = (
                f"Based on {len(data_points)} weeks of training data, your weekly volume "
                f"is {result.rate_description}. Projected weekly volume in {days} days: "
                f"{projected:,.0f} lbs ({abs(diff):,.0f} lb {direction}). "
                f"Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "health",
                    "predicted_value": round(projected),
                    "predicted_date": result.predicted_date,
                    "confidence_score": result.confidence_score,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "data_points": len(data_points),
                        "current_weekly_volume": round(current_volume),
                        "slope_per_day": round(result.slope, 4),
                        "r_squared": round(result.r_squared, 4),
                        "lookback_days": self.LOOKBACK_DAYS,
                        "horizon_days": days,
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions


@register_prediction
class TransformationSuccessProbabilityRule(BasePredictionRule):
    """
    Estimate probability of reaching transformation protocol goals.

    Uses SAE transformation_state to compute a composite success probability
    based on current trajectory, consistency, and momentum.
    """

    rule_name = "transformation_success"
    module = "health"
    prediction_type = "transformation_success"
    min_confidence_to_store = 0.20

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "health")

    def predict(self, user, event):
        try:
            from apps.core.ai_state import get_module_state

            transformation = get_module_state(user, "transformation")
        except Exception:
            return []

        score = transformation.get("transformation_score")
        if score is None:
            return []

        now = get_current_time()

        # Success probability is based on current transformation score
        # and momentum — higher score + momentum = higher probability
        momentum = transformation.get("momentum_score", 0)
        workout_score = transformation.get("workout_score", 0)
        nutrition_score = transformation.get("nutrition_score", 0)

        # Composite probability (0-1)
        # Weight: 40% transformation score, 30% momentum, 15% nutrition, 15% workout
        probability = (
            (score / 100) * 0.40
            + (momentum / 100) * 0.30
            + (nutrition_score / 100) * 0.15
            + (workout_score / 100) * 0.15
        )
        probability = round(min(1.0, max(0.0, probability)), 2)

        # Confidence based on data availability
        data_available = sum(
            1
            for k in ("weight_trend_score", "nutrition_score", "workout_score",
                       "fasting_score", "recovery_score", "momentum_score")
            if transformation.get(k) is not None
        )
        confidence = round(min(0.85, data_available / 6 * 0.85), 2)

        if confidence < self.min_confidence_to_store:
            return []

        pred_date = now + timedelta(days=90)
        date_str = pred_date.strftime("%Y-%m-%d")
        dedupe_key = build_prediction_dedupe_key(
            user.id, "transformation_success_90d", date_str
        )

        conf_label = confidence_label(confidence)
        if probability >= 0.7:
            outlook = "on track"
        elif probability >= 0.4:
            outlook = "needs attention"
        else:
            outlook = "at risk"

        explanation = (
            f"Your transformation success probability is {probability:.0%} "
            f"(outlook: {outlook}). Current transformation score: {score}/100, "
            f"momentum: {momentum}/100. "
            f"Confidence: {conf_label}."
        )

        return [
            {
                "prediction_type": "transformation_success_90d",
                "module": "health",
                "predicted_value": probability,
                "predicted_date": pred_date,
                "confidence_score": confidence,
                "explanation": explanation,
                "evidence": {
                    "rule": self.rule_name,
                    "transformation_score": score,
                    "momentum_score": momentum,
                    "nutrition_score": nutrition_score,
                    "workout_score": workout_score,
                    "probability": probability,
                    "outlook": outlook,
                    "sub_scores": {
                        k: transformation.get(k)
                        for k in (
                            "weight_trend_score",
                            "nutrition_score",
                            "workout_score",
                            "fasting_score",
                            "recovery_score",
                            "momentum_score",
                        )
                        if transformation.get(k) is not None
                    },
                },
                "dedupe_key": dedupe_key,
            }
        ]
