"""
PRIE — Trajectory Engine.

Calculates trajectory from historical data points and projects
future values using linear regression.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from apps.core.ai_predictions.projection_math import (
    calculate_rate_of_change,
    linear_regression,
    project_value,
)


class TrajectoryResult:
    """Result of a trajectory calculation."""

    __slots__ = (
        "predicted_value",
        "predicted_date",
        "confidence_score",
        "slope",
        "intercept",
        "r_squared",
        "data_point_count",
        "rate_description",
    )

    def __init__(
        self,
        predicted_value: float,
        predicted_date: datetime,
        confidence_score: float,
        slope: float,
        intercept: float,
        r_squared: float,
        data_point_count: int,
        rate_description: str,
    ):
        self.predicted_value = predicted_value
        self.predicted_date = predicted_date
        self.confidence_score = confidence_score
        self.slope = slope
        self.intercept = intercept
        self.r_squared = r_squared
        self.data_point_count = data_point_count
        self.rate_description = rate_description


def calculate_linear_projection(
    data_points: list[tuple[datetime, float]],
    days_forward: int,
    unit_label: str = "units",
) -> TrajectoryResult | None:
    """
    Calculate a linear projection from historical data points.

    Args:
        data_points: List of (datetime, value) tuples, chronological order.
        days_forward: Number of days to project into the future.
        unit_label: Human-readable unit name (e.g. "lbs", "%").

    Returns:
        TrajectoryResult or None if insufficient data.
    """
    if len(data_points) < 2:
        return None

    # Sort by date
    sorted_points = sorted(data_points, key=lambda p: p[0])
    base_date = sorted_points[0][0]

    # Convert to x (days since first point) and y (values)
    x_values = []
    y_values = []
    for dt, val in sorted_points:
        days_since_start = (dt - base_date).total_seconds() / 86400.0
        x_values.append(days_since_start)
        y_values.append(float(val))

    slope, intercept, r_squared = linear_regression(x_values, y_values)

    # Project forward
    last_date = sorted_points[-1][0]
    predicted_date = last_date + timedelta(days=days_forward)
    x_target = (predicted_date - base_date).total_seconds() / 86400.0
    predicted_value = project_value(slope, intercept, x_target)

    # Compute confidence from data quality metrics
    from apps.core.ai_predictions.confidence_engine import compute_confidence

    confidence = compute_confidence(
        data_point_count=len(data_points),
        r_squared=r_squared,
        days_of_history=(sorted_points[-1][0] - sorted_points[0][0]).days,
        days_forward=days_forward,
    )

    rate_desc = calculate_rate_of_change(slope, unit_label)

    return TrajectoryResult(
        predicted_value=round(predicted_value, 2),
        predicted_date=predicted_date,
        confidence_score=confidence,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        data_point_count=len(data_points),
        rate_description=rate_desc,
    )
