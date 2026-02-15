"""
PRIE — Prediction Engine.

Main entry point for generating predictions. Iterates registered
prediction rules, deduplicates, and persists results.
"""

import logging

from django.utils import timezone

from apps.core.ai_predictions.models import Prediction, build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import get_prediction_rules

logger = logging.getLogger(__name__)

# Minimum confidence to persist a prediction
MIN_CONFIDENCE_TO_STORE = 0.30


def generate_predictions(user, module=None, record_id=None):
    """
    Generate predictions for a user.

    Args:
        user: Django User instance.
        module: Optional module filter (e.g., "health").
        record_id: Optional record ID for event context.

    Returns:
        List of Prediction instances created/updated.
    """
    event = {
        "event_type": "prediction_check",
        "module": module or "all",
        "record_id": record_id,
        "timestamp_utc": timezone.now().isoformat(),
    }

    rules = get_prediction_rules()
    results = []

    for rule in rules:
        try:
            if not rule.applies(user, event):
                continue

            predictions = rule.predict(user, event)
            for pred_data in predictions:
                confidence = pred_data.get("confidence_score", 0.0)
                min_conf = max(
                    MIN_CONFIDENCE_TO_STORE,
                    getattr(rule, "min_confidence_to_store", 0.30),
                )
                if confidence < min_conf:
                    continue

                prediction = _upsert_prediction(user, pred_data)
                if prediction:
                    results.append(prediction)

        except Exception as e:
            logger.error(
                f"Prediction rule {rule.rule_name} failed for user {user.id}: {e}",
                exc_info=True,
            )

    return results


def _upsert_prediction(user, pred_data):
    """
    Create or update a prediction using dedupe_key.

    If a prediction with the same dedupe_key already exists, supersede
    the old one and create the new one.
    """
    dedupe_key = pred_data.get("dedupe_key", "")
    if not dedupe_key:
        # Build one from available data
        predicted_date = pred_data.get("predicted_date")
        date_str = (
            predicted_date.strftime("%Y-%m-%d") if predicted_date else "unknown"
        )
        dedupe_key = build_prediction_dedupe_key(
            user.id, pred_data["prediction_type"], date_str
        )

    # Supersede existing active prediction with same key
    Prediction.objects.filter(
        user=user,
        dedupe_key=dedupe_key,
        status="active",
    ).update(status="superseded", updated_at=timezone.now())

    # Create new prediction
    prediction = Prediction.objects.create(
        user=user,
        prediction_type=pred_data["prediction_type"],
        module=pred_data["module"],
        predicted_value=pred_data.get("predicted_value"),
        predicted_date=pred_data["predicted_date"],
        confidence_score=pred_data["confidence_score"],
        explanation=pred_data["explanation"],
        evidence=pred_data.get("evidence", {}),
        dedupe_key=dedupe_key,
        status="active",
    )

    logger.info(
        f"Prediction for user {user.id}: {prediction.prediction_type} "
        f"→ {prediction.predicted_value} ({prediction.confidence_score:.0%} confidence)"
    )

    return prediction
