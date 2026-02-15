"""
PRIE — Lab Result prediction rules.

Predictions:
- Lab marker trend direction (up/down/stable) based on historical results
"""

from django.utils import timezone

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.ai_predictions.trajectory_engine import calculate_linear_projection


@register_prediction
class LabMarkerTrendRule(BasePredictionRule):
    """
    Predict lab marker trend direction for markers with multiple results.
    Projects value at next likely test date (90 days out).
    """

    rule_name = "lab_marker_trend"
    module = "labs"
    prediction_type = "lab_marker_trend"
    min_confidence_to_store = 0.25

    PROJECTION_DAYS = 90

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "labs", "medical")

    def predict(self, user, event):
        from apps.medical.models import LabResult

        # Find markers with 2+ numeric results
        results = (
            LabResult.objects.filter(
                user=user,
                value_numeric__isnull=False,
            )
            .order_by("raw_test_name", "collected_at")
            .values_list("raw_test_name", "collected_at", "value_numeric", "unit", "range_low", "range_high")
        )

        # Group by test name
        grouped = {}
        for name, collected_at, value, unit, r_low, r_high in results:
            if name not in grouped:
                grouped[name] = {
                    "points": [],
                    "unit": unit or "",
                    "range_low": r_low,
                    "range_high": r_high,
                }
            grouped[name]["points"].append((collected_at, float(value)))

        predictions = []
        for test_name, data in grouped.items():
            points = data["points"]
            if len(points) < 2:
                continue

            result = calculate_linear_projection(
                points, self.PROJECTION_DAYS, unit_label=data["unit"]
            )
            if result is None:
                continue

            projected = result.predicted_value
            current = points[-1][1]
            diff = projected - current

            # Determine if projected value would be out of range
            range_low = float(data["range_low"]) if data["range_low"] else None
            range_high = float(data["range_high"]) if data["range_high"] else None

            out_of_range = False
            range_note = ""
            if range_low is not None and projected < range_low:
                out_of_range = True
                range_note = f" (below reference range {range_low})"
            elif range_high is not None and projected > range_high:
                out_of_range = True
                range_note = f" (above reference range {range_high})"

            if abs(result.slope) < 0.001 and not out_of_range:
                direction = "stable"
            elif result.slope > 0:
                direction = "upward"
            else:
                direction = "downward"

            conf = confidence_label(result.confidence_score)
            pred_type = f"lab_trend_{test_name[:50]}"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            explanation = (
                f"{test_name}: {result.data_point_count} results show a "
                f"{direction} trend ({result.rate_description}). "
                f"Projected value in {self.PROJECTION_DAYS} days: "
                f"{projected:.1f} {data['unit']}{range_note}. "
                f"Current: {current:.1f} {data['unit']}. Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "labs",
                    "predicted_value": projected,
                    "predicted_date": result.predicted_date,
                    "confidence_score": result.confidence_score,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "test_name": test_name,
                        "data_points": result.data_point_count,
                        "current_value": current,
                        "projected_value": projected,
                        "slope_per_day": round(result.slope, 4),
                        "r_squared": round(result.r_squared, 4),
                        "direction": direction,
                        "out_of_range": out_of_range,
                        "unit": data["unit"],
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions
