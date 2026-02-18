"""
Phase 4 CoS — Prediction Validator.

Compares past PRIE predictions against actual outcomes.
Computes accuracy scores and adjusts confidence dynamically.

Public API:
    - validate_expired_predictions(user) -> list[PredictionOutcome]
    - get_accuracy_profile(user, prediction_type) -> PredictionAccuracyProfile
    - get_confidence_adjustment(user, prediction_type) -> float
"""

import logging

from django.utils import timezone

from apps.core.ai_feedback.models import (
    PredictionAccuracyProfile,
    PredictionOutcome,
)
from apps.core.ai_predictions.models import Prediction

logger = logging.getLogger(__name__)


def validate_expired_predictions(user):
    """
    Find predictions past their predicted_date and validate against actuals.

    Only validates predictions that:
    - Have status='active' or 'expired'
    - Have a predicted_date in the past
    - Don't already have an outcome recorded

    Returns:
        List of PredictionOutcome instances created.
    """
    now = timezone.now()
    outcomes = []

    predictions = Prediction.objects.filter(
        user=user,
        predicted_date__lte=now,
    ).exclude(
        outcome__isnull=False,  # skip already validated
    ).select_related("outcome")

    # Filter to only those without outcomes (the exclude above handles this
    # but we double-check in case of race conditions)
    to_validate = [p for p in predictions if not hasattr(p, 'outcome') or not PredictionOutcome.objects.filter(prediction=p).exists()]

    for prediction in to_validate:
        try:
            actual = _get_actual_value(user, prediction)
            if actual is None:
                continue  # no data available yet

            outcome = _record_outcome(prediction, user, actual)
            if outcome:
                outcomes.append(outcome)
                _update_accuracy_profile(user, prediction.prediction_type)

                # Mark prediction as expired if still active
                if prediction.status == "active":
                    prediction.status = "expired"
                    prediction.save(update_fields=["status", "updated_at"])

        except Exception as e:
            logger.error(
                f"PredictionValidator: Failed to validate prediction "
                f"{prediction.id} for user {user.id}: {e}",
                exc_info=True,
            )

    return outcomes


def get_accuracy_profile(user, prediction_type):
    """Get the accuracy profile for a user and prediction type."""
    profile, _ = PredictionAccuracyProfile.objects.get_or_create(
        user=user,
        prediction_type=prediction_type,
    )
    return profile


def get_confidence_adjustment(user, prediction_type):
    """
    Get the confidence adjustment factor for a prediction type.

    Returns:
        float: -0.3 to +0.2 adjustment to apply to future predictions.
    """
    try:
        profile = PredictionAccuracyProfile.objects.filter(
            user=user,
            prediction_type=prediction_type,
        ).first()
        if profile and profile.total_validated >= 3:
            return profile.confidence_adjustment
    except Exception:
        pass
    return 0.0


def _record_outcome(prediction, user, actual_value):
    """Create a PredictionOutcome record."""
    predicted = prediction.predicted_value
    if predicted is None:
        return None

    error_abs = abs(predicted - actual_value)
    error_pct = (error_abs / abs(actual_value) * 100) if actual_value != 0 else 0.0
    # Accuracy: 1.0 for perfect, decays with error
    accuracy = max(0.0, 1.0 - (error_pct / 100.0))

    return PredictionOutcome.objects.create(
        prediction=prediction,
        user=user,
        actual_value=actual_value,
        error_abs=round(error_abs, 4),
        error_pct=round(error_pct, 2),
        accuracy_score=round(accuracy, 4),
    )


def _update_accuracy_profile(user, prediction_type):
    """Update the aggregate accuracy profile after a new outcome."""
    profile, _ = PredictionAccuracyProfile.objects.get_or_create(
        user=user,
        prediction_type=prediction_type,
    )

    outcomes = PredictionOutcome.objects.filter(
        user=user,
        prediction__prediction_type=prediction_type,
    )

    count = outcomes.count()
    if count == 0:
        return

    from django.db.models import Avg, Count, Q

    stats = outcomes.aggregate(
        avg_accuracy=Avg("accuracy_score"),
        avg_error=Avg("error_pct"),
        accurate_count=Count("id", filter=Q(accuracy_score__gte=0.7)),
    )

    profile.total_validated = count
    profile.total_accurate = stats["accurate_count"] or 0
    profile.avg_accuracy = round(stats["avg_accuracy"] or 0.5, 4)
    profile.avg_error_pct = round(stats["avg_error"] or 0.0, 2)

    # Confidence adjustment: good track record boosts, poor record penalizes
    if count >= 3:
        if profile.avg_accuracy >= 0.8:
            profile.confidence_adjustment = 0.1
        elif profile.avg_accuracy >= 0.6:
            profile.confidence_adjustment = 0.0
        elif profile.avg_accuracy >= 0.4:
            profile.confidence_adjustment = -0.1
        else:
            profile.confidence_adjustment = -0.2

    profile.save()


def _get_actual_value(user, prediction):
    """
    Retrieve the actual value for a prediction based on its type and module.

    Returns float or None if data not available.
    """
    ptype = prediction.prediction_type
    module = prediction.module

    try:
        if module == "health" and "weight" in ptype:
            from apps.health.models import WeightEntry
            entry = WeightEntry.objects.filter(
                user=user,
                recorded_at__date__lte=prediction.predicted_date.date(),
            ).order_by("-recorded_at").first()
            return entry.value if entry else None

        if module == "health" and "body_fat" in ptype:
            from apps.health.models import BodyCompositionEntry
            entry = BodyCompositionEntry.objects.filter(
                user=user,
                metric_name="body_fat_pct",
                measurement_date__lte=prediction.predicted_date.date(),
            ).order_by("-measurement_date").first()
            return entry.value if entry else None

        if module in ("goals", "purpose") and "completion" in ptype:
            from apps.purpose.models import LifeGoal
            goal_count = LifeGoal.objects.filter(
                user=user,
                status="completed",
            ).count()
            return float(goal_count)

        if module in ("habits", "purpose") and "streak" in ptype:
            from apps.purpose.models import HabitGoal
            habit = HabitGoal.objects.filter(
                user=user,
                status="active",
            ).first()
            if habit and hasattr(habit, "current_streak"):
                return float(habit.current_streak)

    except Exception as e:
        logger.debug(f"PredictionValidator: Could not get actual for {ptype}: {e}")

    return None
