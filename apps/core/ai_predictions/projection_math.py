"""
PRIE — Deterministic projection math.

Simple linear regression using pure Python (no numpy required).
All projections are explainable and auditable.
"""

from __future__ import annotations


def linear_regression(x_values: list[float], y_values: list[float]):
    """
    Simple linear regression: y = slope * x + intercept.

    Args:
        x_values: Independent variable (typically days since first point).
        y_values: Dependent variable (the measured value).

    Returns:
        (slope, intercept, r_squared) tuple.
        r_squared indicates goodness of fit (0-1).
    """
    n = len(x_values)
    if n < 2:
        return 0.0, y_values[0] if y_values else 0.0, 0.0

    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    sum_x2 = sum(x * x for x in x_values)

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return 0.0, sum_y / n, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    # R-squared
    mean_y = sum_y / n
    ss_tot = sum((y - mean_y) ** 2 for y in y_values)
    if ss_tot == 0:
        r_squared = 1.0  # All values identical → perfect fit
    else:
        ss_res = sum(
            (y - (slope * x + intercept)) ** 2
            for x, y in zip(x_values, y_values)
        )
        r_squared = max(0.0, 1.0 - ss_res / ss_tot)

    return slope, intercept, r_squared


def project_value(slope: float, intercept: float, x_target: float) -> float:
    """Project a value at x_target using the regression line."""
    return slope * x_target + intercept


def calculate_rate_of_change(slope: float, unit_label: str = "units") -> str:
    """Human-readable rate of change description."""
    abs_slope = abs(slope)
    direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"

    if abs_slope < 0.01:
        return f"approximately stable"

    per_day = abs_slope
    per_week = abs_slope * 7
    per_month = abs_slope * 30

    if per_day >= 1.0:
        return f"{direction} ~{per_day:.1f} {unit_label}/day"
    elif per_week >= 1.0:
        return f"{direction} ~{per_week:.1f} {unit_label}/week"
    else:
        return f"{direction} ~{per_month:.1f} {unit_label}/month"
