"""
PRIE — Confidence Engine.

Computes confidence scores for predictions based on data quality:
- Number of data points
- Consistency of trend (R²)
- Recency of data
- Projection distance
"""


def compute_confidence(
    data_point_count: int,
    r_squared: float,
    days_of_history: int,
    days_forward: int,
) -> float:
    """
    Compute confidence score (0.0-1.0) for a prediction.

    Factors:
        1. Data volume: more points → higher confidence
        2. Trend consistency: higher R² → higher confidence
        3. History ratio: longer history relative to projection → higher
        4. Projection distance: further out → lower confidence

    Returns:
        Float 0.0-1.0
    """
    # Factor 1: Data volume (0-0.3)
    if data_point_count >= 20:
        volume_score = 0.30
    elif data_point_count >= 10:
        volume_score = 0.25
    elif data_point_count >= 5:
        volume_score = 0.18
    elif data_point_count >= 3:
        volume_score = 0.10
    else:
        volume_score = 0.05

    # Factor 2: Trend consistency / R² (0-0.30)
    consistency_score = r_squared * 0.30

    # Factor 3: History-to-projection ratio (0-0.20)
    if days_of_history > 0 and days_forward > 0:
        ratio = days_of_history / days_forward
        if ratio >= 3.0:
            history_score = 0.20
        elif ratio >= 2.0:
            history_score = 0.15
        elif ratio >= 1.0:
            history_score = 0.10
        else:
            history_score = 0.05
    else:
        history_score = 0.05

    # Factor 4: Projection distance penalty (0-0.20)
    if days_forward <= 30:
        distance_score = 0.20
    elif days_forward <= 60:
        distance_score = 0.15
    elif days_forward <= 90:
        distance_score = 0.10
    else:
        distance_score = 0.05

    total = volume_score + consistency_score + history_score + distance_score
    return round(min(1.0, max(0.0, total)), 2)


def confidence_label(score: float) -> str:
    """Human-readable confidence label."""
    if score >= 0.75:
        return "high"
    elif score >= 0.50:
        return "medium"
    elif score >= 0.30:
        return "low"
    else:
        return "very low"
