"""
PRIE — Health prediction rules.

Predictions:
- Projected weight at 30, 60, 90 days
"""

from datetime import timedelta

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.ai_predictions.trajectory_engine import calculate_linear_projection
from apps.core.time.system_clock import get_current_time


@register_prediction
class WeightProjectionRule(BasePredictionRule):
    """Project weight at 30, 60, 90 days based on recent trends."""

    rule_name = "weight_projection"
    module = "health"
    prediction_type = "weight_projection"
    min_confidence_to_store = 0.25

    HORIZONS = [30, 60, 90]
    LOOKBACK_DAYS = 90

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "health")

    def predict(self, user, event):
        from apps.health.models import WeightEntry

        cutoff = get_current_time() - timedelta(days=self.LOOKBACK_DAYS)
        entries = (
            WeightEntry.objects.filter(
                user=user,
                recorded_at__gte=cutoff,
            )
            .order_by("recorded_at")
            .values_list("recorded_at", "value")
        )

        data_points = [(dt, float(val)) for dt, val in entries]
        if len(data_points) < 2:
            return []

        predictions = []
        for days in self.HORIZONS:
            result = calculate_linear_projection(data_points, days, unit_label="lbs")
            if result is None:
                continue

            pred_type = f"weight_{days}d"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            current_weight = data_points[-1][1]
            projected = result.predicted_value
            diff = projected - current_weight
            direction = "gain" if diff > 0 else "loss" if diff < 0 else "no change"
            conf = confidence_label(result.confidence_score)

            explanation = (
                f"Based on {result.data_point_count} weight entries over the past "
                f"{self.LOOKBACK_DAYS} days, your weight is {result.rate_description}. "
                f"At this rate, your projected weight in {days} days is "
                f"{projected:.1f} lbs ({abs(diff):.1f} lb {direction}). "
                f"Confidence: {conf}."
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
                        "current_weight": current_weight,
                        "slope_per_day": round(result.slope, 4),
                        "r_squared": round(result.r_squared, 4),
                        "lookback_days": self.LOOKBACK_DAYS,
                        "horizon_days": days,
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions
