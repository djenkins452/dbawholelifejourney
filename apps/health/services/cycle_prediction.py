"""
Cycle Prediction Service

Generates predictions for next period and fertile window based on historical
cycle data. Uses weighted moving averages for more accurate predictions.

Key Features:
- Weighted moving average (recent cycles weighted higher)
- Confidence scores based on cycle regularity
- Fertile window calculation adjusted for cycle length
- Minimum 3 completed cycles required for predictions

Usage:
    from apps.health.services.cycle_prediction import CyclePredictionService

    service = CyclePredictionService(user)
    prediction = service.generate_prediction()
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import stdev
from typing import Optional

from django.utils import timezone

from ..models import Cycle, CyclePrediction, CycleSettings


# Algorithm version for tracking
ALGORITHM_VERSION = "v1.0-wma"

# Minimum cycles needed for predictions
MIN_CYCLES_FOR_PREDICTION = 3

# Maximum cycles to consider for prediction
MAX_CYCLES_FOR_PREDICTION = 6

# Weights for weighted moving average (most recent first)
# More recent cycles have higher weight
CYCLE_WEIGHTS = [3.0, 2.5, 2.0, 1.5, 1.0, 0.5]

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.80
MEDIUM_CONFIDENCE_THRESHOLD = 0.60
LOW_CONFIDENCE_THRESHOLD = 0.40

# Standard cycle assumptions for fertile window calculation
# Fertile window typically days 10-17 of a 28-day cycle
STANDARD_CYCLE_LENGTH = 28
FERTILE_WINDOW_START_DAY = 10  # In standard 28-day cycle
FERTILE_WINDOW_END_DAY = 17  # In standard 28-day cycle


@dataclass
class PredictionResult:
    """Result of prediction calculation."""

    predicted_period_start: date
    predicted_period_end: date
    predicted_fertile_start: Optional[date]
    predicted_fertile_end: Optional[date]
    confidence: Decimal
    confidence_level: str
    predicted_cycle_length: int
    predicted_period_length: int
    cycles_analyzed: int


class CyclePredictionService:
    """
    Service for predicting menstrual cycle events.

    Uses weighted moving averages of historical cycle data to generate
    predictions for next period and fertile window.
    """

    def __init__(self, user):
        """
        Initialize the prediction service for a specific user.

        Args:
            user: The User instance to generate predictions for
        """
        self.user = user
        self._settings = None
        self._cycles = None

    @property
    def settings(self) -> Optional[CycleSettings]:
        """Get user's cycle settings (cached)."""
        if self._settings is None:
            try:
                self._settings = CycleSettings.objects.get(user=self.user)
            except CycleSettings.DoesNotExist:
                pass
        return self._settings

    @property
    def completed_cycles(self) -> list:
        """Get completed cycles for analysis (cached)."""
        if self._cycles is None:
            self._cycles = list(
                Cycle.objects.filter(
                    user=self.user,
                    end_date__isnull=False,  # Must be completed
                ).order_by("-start_date")[:MAX_CYCLES_FOR_PREDICTION]
            )
        return self._cycles

    def can_generate_prediction(self) -> tuple[bool, str]:
        """
        Check if we can generate a prediction for this user.

        Returns:
            Tuple of (can_predict, reason)
        """
        if not self.settings or not self.settings.is_enabled:
            return False, "Cycle tracking not enabled"

        if len(self.completed_cycles) < MIN_CYCLES_FOR_PREDICTION:
            return (
                False,
                f"Need at least {MIN_CYCLES_FOR_PREDICTION} completed cycles, "
                f"have {len(self.completed_cycles)}",
            )

        return True, "OK"

    def generate_prediction(
        self, save: bool = True
    ) -> Optional[PredictionResult]:
        """
        Generate a new prediction based on historical data.

        Args:
            save: Whether to save the prediction to the database

        Returns:
            PredictionResult or None if prediction cannot be generated
        """
        can_predict, reason = self.can_generate_prediction()
        if not can_predict:
            return None

        # Calculate weighted averages
        avg_cycle_length = self._calculate_weighted_cycle_length()
        avg_period_length = self._calculate_weighted_period_length()

        # Get the most recent cycle's end date to predict from
        current_cycle = Cycle.objects.filter(
            user=self.user,
            end_date__isnull=True,
        ).first()

        if current_cycle:
            # Predict from current ongoing cycle's start
            prediction_base = current_cycle.start_date
        else:
            # Predict from most recent completed cycle's end + 1
            most_recent = self.completed_cycles[0]
            prediction_base = most_recent.end_date + timedelta(days=1)

        # Calculate predicted dates
        predicted_period_start = prediction_base + timedelta(days=avg_cycle_length)
        predicted_period_end = predicted_period_start + timedelta(
            days=avg_period_length - 1
        )

        # Calculate fertile window (if enabled)
        fertile_start = None
        fertile_end = None
        if self.settings and self.settings.fertile_window_tracking_enabled:
            fertile_start, fertile_end = self._calculate_fertile_window(
                prediction_base, avg_cycle_length
            )

        # Calculate confidence score
        confidence = self._calculate_confidence()
        confidence_level = self._get_confidence_level(confidence)

        result = PredictionResult(
            predicted_period_start=predicted_period_start,
            predicted_period_end=predicted_period_end,
            predicted_fertile_start=fertile_start,
            predicted_fertile_end=fertile_end,
            confidence=confidence,
            confidence_level=confidence_level,
            predicted_cycle_length=avg_cycle_length,
            predicted_period_length=avg_period_length,
            cycles_analyzed=len(self.completed_cycles),
        )

        # Save to database if requested
        if save:
            self._save_prediction(result)

        return result

    def _calculate_weighted_cycle_length(self) -> int:
        """
        Calculate weighted average cycle length.

        More recent cycles are weighted higher.

        Returns:
            Weighted average cycle length (rounded to nearest integer)
        """
        cycles = self.completed_cycles
        if not cycles:
            return self.settings.average_cycle_length if self.settings else 28

        total_weight = 0
        weighted_sum = 0

        for i, cycle in enumerate(cycles):
            if cycle.cycle_length is None:
                continue
            weight = CYCLE_WEIGHTS[min(i, len(CYCLE_WEIGHTS) - 1)]
            weighted_sum += cycle.cycle_length * weight
            total_weight += weight

        if total_weight == 0:
            return self.settings.average_cycle_length if self.settings else 28

        return round(weighted_sum / total_weight)

    def _calculate_weighted_period_length(self) -> int:
        """
        Calculate weighted average period length.

        More recent cycles are weighted higher.

        Returns:
            Weighted average period length (rounded to nearest integer)
        """
        cycles = self.completed_cycles
        if not cycles:
            return self.settings.average_period_length if self.settings else 5

        total_weight = 0
        weighted_sum = 0

        for i, cycle in enumerate(cycles):
            if cycle.period_length is None:
                continue
            weight = CYCLE_WEIGHTS[min(i, len(CYCLE_WEIGHTS) - 1)]
            weighted_sum += cycle.period_length * weight
            total_weight += weight

        if total_weight == 0:
            return self.settings.average_period_length if self.settings else 5

        return round(weighted_sum / total_weight)

    def _calculate_fertile_window(
        self, cycle_start: date, cycle_length: int
    ) -> tuple[Optional[date], Optional[date]]:
        """
        Calculate predicted fertile window dates.

        Adjusts the standard fertile window (days 10-17) proportionally
        for the user's predicted cycle length.

        Args:
            cycle_start: Start date of the cycle to predict for
            cycle_length: Predicted cycle length

        Returns:
            Tuple of (fertile_start, fertile_end) dates
        """
        # Scale fertile window proportionally to cycle length
        scale = cycle_length / STANDARD_CYCLE_LENGTH

        fertile_start_day = round(FERTILE_WINDOW_START_DAY * scale)
        fertile_end_day = round(FERTILE_WINDOW_END_DAY * scale)

        # Ensure window is at least 5 days
        if fertile_end_day - fertile_start_day < 5:
            fertile_end_day = fertile_start_day + 5

        fertile_start = cycle_start + timedelta(days=fertile_start_day - 1)
        fertile_end = cycle_start + timedelta(days=fertile_end_day - 1)

        return fertile_start, fertile_end

    def _calculate_confidence(self) -> Decimal:
        """
        Calculate prediction confidence score based on cycle regularity.

        Uses standard deviation of cycle lengths. More regular cycles
        result in higher confidence.

        Returns:
            Confidence score from 0.00 to 1.00
        """
        cycles = self.completed_cycles
        cycle_lengths = [c.cycle_length for c in cycles if c.cycle_length]

        if len(cycle_lengths) < 2:
            # Not enough data for variance calculation
            return Decimal("0.50")

        # Calculate standard deviation
        try:
            std_dev = stdev(cycle_lengths)
        except Exception:
            return Decimal("0.50")

        # Convert std_dev to confidence score
        # Lower std_dev = higher confidence
        # std_dev of 0 = perfect regularity = 1.0 confidence
        # std_dev of 7+ days = low confidence = 0.3

        if std_dev <= 1:
            confidence = 0.95
        elif std_dev <= 2:
            confidence = 0.85
        elif std_dev <= 3:
            confidence = 0.75
        elif std_dev <= 4:
            confidence = 0.65
        elif std_dev <= 5:
            confidence = 0.55
        elif std_dev <= 6:
            confidence = 0.45
        else:
            confidence = 0.35

        # Adjust for number of cycles (more data = slightly higher confidence)
        cycle_bonus = min(0.05, len(cycle_lengths) * 0.01)
        confidence = min(0.99, confidence + cycle_bonus)

        return Decimal(str(round(confidence, 2)))

    def _get_confidence_level(self, confidence: Decimal) -> str:
        """
        Get human-readable confidence level.

        Args:
            confidence: Confidence score (0.00 to 1.00)

        Returns:
            String confidence level (high, medium, low)
        """
        if float(confidence) >= HIGH_CONFIDENCE_THRESHOLD:
            return "high"
        elif float(confidence) >= MEDIUM_CONFIDENCE_THRESHOLD:
            return "medium"
        elif float(confidence) >= LOW_CONFIDENCE_THRESHOLD:
            return "low"
        else:
            return "very_low"

    def _save_prediction(self, result: PredictionResult) -> CyclePrediction:
        """
        Save prediction to database.

        Args:
            result: PredictionResult to save

        Returns:
            Created CyclePrediction instance
        """
        return CyclePrediction.objects.create(
            user=self.user,
            predicted_period_start=result.predicted_period_start,
            predicted_period_end=result.predicted_period_end,
            predicted_fertile_window_start=result.predicted_fertile_start,
            predicted_fertile_window_end=result.predicted_fertile_end,
            prediction_confidence=result.confidence,
            prediction_algorithm_version=ALGORITHM_VERSION,
        )

    def get_latest_prediction(self) -> Optional[CyclePrediction]:
        """
        Get the most recent prediction for this user.

        Returns:
            Latest CyclePrediction or None
        """
        return CyclePrediction.objects.filter(user=self.user).first()

    def get_prediction_accuracy_stats(self) -> dict:
        """
        Calculate accuracy statistics from past predictions.

        Returns:
            Dictionary with accuracy metrics
        """
        predictions = CyclePrediction.objects.filter(
            user=self.user,
            actual_period_start__isnull=False,
        )

        if not predictions.exists():
            return {
                "total_predictions": 0,
                "verified_predictions": 0,
                "average_accuracy_days": None,
                "accuracy_within_3_days": None,
            }

        accuracies = [p.accuracy for p in predictions if p.accuracy is not None]

        if not accuracies:
            return {
                "total_predictions": predictions.count(),
                "verified_predictions": 0,
                "average_accuracy_days": None,
                "accuracy_within_3_days": None,
            }

        # Calculate metrics
        abs_accuracies = [abs(a) for a in accuracies]
        within_3_days = sum(1 for a in abs_accuracies if a <= 3)

        return {
            "total_predictions": CyclePrediction.objects.filter(
                user=self.user
            ).count(),
            "verified_predictions": len(accuracies),
            "average_accuracy_days": round(
                sum(abs_accuracies) / len(abs_accuracies), 1
            ),
            "accuracy_within_3_days": round(
                (within_3_days / len(accuracies)) * 100, 1
            ),
        }
