"""
PRIE — Prediction Engine.

Main entry point for generating predictions. Iterates registered
prediction rules, deduplicates, and persists results.

Data Abstraction Layer:
    get_prediction_input_data() provides a single data-access gateway for
    prediction rules. When SAE (State Awareness Engine) is installed, this
    function will read from cached user state instead of hitting the database
    directly, improving performance and enabling state-aware predictions.
"""

import logging

from apps.core.ai_predictions.models import Prediction, build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import get_prediction_rules
from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run
from apps.core.time.system_clock import get_current_time

logger = logging.getLogger(__name__)

# Minimum confidence to persist a prediction
MIN_CONFIDENCE_TO_STORE = 0.30


def get_prediction_input_data(user, module, data_type, lookback_days=90):
    """
    Abstraction layer for prediction data access.

    When SAE (State Awareness Engine) is installed, this reads from cached
    user state. Otherwise, falls back to direct database queries.

    Args:
        user: Django User instance.
        module: Module name (e.g., "health", "goals", "habits").
        data_type: Type of data to retrieve (e.g., "weight_entries",
                   "body_fat_entries", "habit_entries", "goal_milestones",
                   "lab_results").
        lookback_days: Number of days to look back for data.

    Returns:
        QuerySet or list of data appropriate for the requested data_type.
        Returns empty list if SAE lookup fails and no fallback available.
    """
    # ── Step 1: Try SAE (State Awareness Engine) if installed ──────────
    try:
        from apps.core.ai_state.state_reader import get_cached_data  # noqa: F401

        cached = get_cached_data(user, module, data_type, lookback_days)
        if cached is not None:
            return cached
    except ImportError:
        pass  # SAE not yet installed — expected
    except Exception as e:
        logger.warning(
            f"SAE data read failed for user {user.id}, module={module}, "
            f"type={data_type}: {e}. Falling back to database."
        )

    # ── Step 2: Direct database fallback ───────────────────────────────
    now = get_current_time()
    cutoff = now - __import__("datetime").timedelta(days=lookback_days)

    if module == "health" and data_type == "weight_entries":
        from apps.health.models import WeightEntry

        return (
            WeightEntry.objects.filter(
                user=user,
                recorded_at__gte=cutoff,
            )
            .order_by("recorded_at")
            .values_list("recorded_at", "value")
        )

    if module == "health" and data_type in ("body_fat_entries", "lean_mass_entries"):
        from apps.health.models import BodyCompositionEntry

        metric = "body_fat_pct" if data_type == "body_fat_entries" else "lean_mass"
        return (
            BodyCompositionEntry.objects.filter(
                user=user,
                metric_name=metric,
                measurement_date__gte=cutoff.date(),
            )
            .order_by("measurement_date")
            .values_list("measurement_date", "value")
        )

    if module in ("goals", "purpose") and data_type == "active_goals":
        from apps.purpose.models import LifeGoal

        return LifeGoal.objects.filter(
            user=user,
            status="active",
            target_date__isnull=False,
        )

    if module in ("habits", "purpose") and data_type == "active_habits":
        from apps.purpose.models import HabitGoal

        return HabitGoal.objects.filter(user=user, status="active")

    if module in ("labs", "medical") and data_type == "lab_results":
        from apps.medical.models import LabResult

        return (
            LabResult.objects.filter(
                user=user,
                value_numeric__isnull=False,
            )
            .order_by("raw_test_name", "collected_at")
            .values_list(
                "raw_test_name", "collected_at", "value_numeric",
                "unit", "range_low", "range_high",
            )
        )

    # Unknown data_type — return empty list
    logger.warning(
        f"Unknown prediction data type: module={module}, type={data_type}"
    )
    return []


@_instrument_engine_run("PRIE", 3)
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
    now = get_current_time()
    event = {
        "event_type": "prediction_check",
        "module": module or "all",
        "record_id": record_id,
        "timestamp_utc": now.isoformat(),
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

                # Phase 4: Apply feedback-based confidence adjustment
                try:
                    from apps.core.ai_feedback.prediction_validator import get_confidence_adjustment
                    adjustment = get_confidence_adjustment(
                        user, pred_data.get("prediction_type", "")
                    )
                    confidence = max(0.0, min(1.0, confidence + adjustment))
                    pred_data["confidence_score"] = confidence
                except Exception:
                    pass  # Feedback adjustment must never break predictions

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
    ).update(status="superseded", updated_at=get_current_time())

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
