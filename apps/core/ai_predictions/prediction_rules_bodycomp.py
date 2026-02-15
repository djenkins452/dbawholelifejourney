"""
PRIE — Body Composition prediction rules.

Predictions:
- Projected body fat percentage at 30, 60, 90 days
- Projected lean body mass trends
"""

from datetime import timedelta

from django.utils import timezone

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.ai_predictions.trajectory_engine import calculate_linear_projection
from apps.core.time.system_clock import get_current_time


@register_prediction
class BodyFatProjectionRule(BasePredictionRule):
    """Project body fat percentage at 30, 60, 90 days."""

    rule_name = "body_fat_projection"
    module = "health"
    prediction_type = "body_fat_projection"
    min_confidence_to_store = 0.25

    HORIZONS = [30, 60, 90]
    LOOKBACK_DAYS = 120

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "health")

    def predict(self, user, event):
        from apps.health.models import BodyCompositionEntry

        cutoff = get_current_time() - timedelta(days=self.LOOKBACK_DAYS)
        entries = (
            BodyCompositionEntry.objects.filter(
                user=user,
                metric_name="body_fat_pct",
                measurement_date__gte=cutoff.date(),
            )
            .order_by("measurement_date")
            .values_list("measurement_date", "value")
        )

        data_points = [
            (timezone.make_aware(
                timezone.datetime.combine(d, timezone.datetime.min.time())
            ), float(val))
            for d, val in entries
        ]
        if len(data_points) < 2:
            return []

        predictions = []
        for days in self.HORIZONS:
            result = calculate_linear_projection(data_points, days, unit_label="%")
            if result is None:
                continue

            pred_type = f"body_fat_{days}d"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            current_bf = data_points[-1][1]
            projected = result.predicted_value
            diff = projected - current_bf
            direction = "increase" if diff > 0 else "decrease" if diff < 0 else "no change"
            conf = confidence_label(result.confidence_score)

            explanation = (
                f"Based on {result.data_point_count} body fat measurements, "
                f"your body fat percentage is {result.rate_description}. "
                f"Projected body fat in {days} days: {projected:.1f}% "
                f"({abs(diff):.1f}% {direction}). Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "health",
                    "predicted_value": projected,
                    "predicted_date": result.predicted_date,
                    "confidence_score": result.confidence_score,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "data_points": result.data_point_count,
                        "current_body_fat": current_bf,
                        "slope_per_day": round(result.slope, 4),
                        "r_squared": round(result.r_squared, 4),
                        "horizon_days": days,
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions


@register_prediction
class LeanMassProjectionRule(BasePredictionRule):
    """Project lean body mass trends at 30, 60, 90 days."""

    rule_name = "lean_mass_projection"
    module = "health"
    prediction_type = "lean_mass_projection"
    min_confidence_to_store = 0.25

    HORIZONS = [30, 60, 90]
    LOOKBACK_DAYS = 120

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "health")

    def predict(self, user, event):
        from apps.health.models import BodyCompositionEntry

        cutoff = get_current_time() - timedelta(days=self.LOOKBACK_DAYS)
        entries = (
            BodyCompositionEntry.objects.filter(
                user=user,
                metric_name="lean_mass",
                measurement_date__gte=cutoff.date(),
            )
            .order_by("measurement_date")
            .values_list("measurement_date", "value")
        )

        data_points = [
            (timezone.make_aware(
                timezone.datetime.combine(d, timezone.datetime.min.time())
            ), float(val))
            for d, val in entries
        ]
        if len(data_points) < 2:
            return []

        predictions = []
        for days in self.HORIZONS:
            result = calculate_linear_projection(data_points, days, unit_label="lbs")
            if result is None:
                continue

            pred_type = f"lean_mass_{days}d"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            current = data_points[-1][1]
            projected = result.predicted_value
            diff = projected - current
            direction = "gain" if diff > 0 else "loss" if diff < 0 else "no change"
            conf = confidence_label(result.confidence_score)

            explanation = (
                f"Based on {result.data_point_count} lean mass measurements, "
                f"your lean mass is {result.rate_description}. "
                f"Projected lean mass in {days} days: {projected:.1f} lbs "
                f"({abs(diff):.1f} lb {direction}). Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "health",
                    "predicted_value": projected,
                    "predicted_date": result.predicted_date,
                    "confidence_score": result.confidence_score,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "data_points": result.data_point_count,
                        "current_lean_mass": current,
                        "slope_per_day": round(result.slope, 4),
                        "r_squared": round(result.r_squared, 4),
                        "horizon_days": days,
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions
