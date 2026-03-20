"""
Pattern Utilities — Reusable analysis functions for insight rules.

Simple, explainable, no ML required.
"""

from datetime import timedelta

from apps.core.time.system_clock import get_current_time


def get_time_window(reference_time=None, days=14):
    """
    Get a (start, end) tuple for a time window.

    Args:
        reference_time: End of window (defaults to now).
        days: Window size in days.

    Returns:
        (window_start, window_end) as timezone-aware datetimes.
    """
    end = reference_time or get_current_time()
    start = end - timedelta(days=days)
    return start, end


def compute_simple_trend(values_with_dates):
    """
    Compute directional trend from a list of (date, value) tuples.

    Returns:
        Dict with:
        - direction: "up", "down", or "flat"
        - first_value: First chronological value
        - last_value: Last chronological value
        - net_change: last - first
        - count: Number of data points
    """
    if not values_with_dates or len(values_with_dates) < 2:
        return None

    sorted_vals = sorted(values_with_dates, key=lambda x: x[0])
    first_val = float(sorted_vals[0][1])
    last_val = float(sorted_vals[-1][1])
    net_change = last_val - first_val

    if abs(net_change) < 0.01:
        direction = "flat"
    elif net_change > 0:
        direction = "up"
    else:
        direction = "down"

    return {
        "direction": direction,
        "first_value": first_val,
        "last_value": last_val,
        "net_change": round(net_change, 2),
        "count": len(sorted_vals),
    }


def percent_change(old, new):
    """Calculate percent change between two values."""
    if old == 0:
        return 0.0
    return round(((new - old) / abs(old)) * 100, 1)


def requires_min_points(values, n):
    """Check if we have at least n data points."""
    return len(values) >= n


def days_since(dt):
    """Calculate days since a given datetime."""
    if not dt:
        return None
    now = get_current_time()
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        # Make naive datetime aware for comparison
        from django.utils.timezone import make_aware
        dt = make_aware(dt)
    delta = now - dt
    return delta.days


def compute_rolling_stress_score(daily_stress_values, decay_factor=0.85):
    """
    Compute a rolling stress score using exponential decay.

    Stress persistence: recent stress carries more weight than older stress.
    A single bad day decays quickly; sustained stress accumulates.

    Args:
        daily_stress_values: list of (date, stress_value) tuples, ordered
            chronologically. stress_value is typically 0.0 (no stress) to
            1.0 (high stress), derived from emotion selections.
        decay_factor: How much yesterday's score carries forward (0.0-1.0).
            Default 0.85 means ~50% decay in 4 days.

    Returns:
        Dict with:
        - score: Current rolling stress score (0.0 = no stress, >1.0 = sustained)
        - trend: "rising", "falling", or "stable"
        - days_elevated: Number of consecutive days score was > 0.3
        - peak_score: Highest daily score in the window
        - data_points: Number of data points used

    Example:
        Single stress day:  day1=0.4 → score=0.4 → next day: 0.4*0.85=0.34
        Sustained 3 days:   0.4 → 0.74 → 1.03  (accumulates)
    """
    if not daily_stress_values:
        return {
            'score': 0.0,
            'trend': 'stable',
            'days_elevated': 0,
            'peak_score': 0.0,
            'data_points': 0,
        }

    sorted_vals = sorted(daily_stress_values, key=lambda x: x[0])
    score = 0.0
    peak = 0.0
    days_elevated = 0
    scores_history = []

    for _date, stress_val in sorted_vals:
        score = (score * decay_factor) + float(stress_val)
        peak = max(peak, score)
        scores_history.append(score)
        if score > 0.3:
            days_elevated += 1
        else:
            days_elevated = 0  # Reset consecutive count

    # Trend: compare first half vs second half of scores
    trend = 'stable'
    if len(scores_history) >= 4:
        mid = len(scores_history) // 2
        first_avg = sum(scores_history[:mid]) / mid
        second_avg = sum(scores_history[mid:]) / (len(scores_history) - mid)
        diff = second_avg - first_avg
        if diff > 0.15:
            trend = 'rising'
        elif diff < -0.15:
            trend = 'falling'

    return {
        'score': round(score, 2),
        'trend': trend,
        'days_elevated': days_elevated,
        'peak_score': round(peak, 2),
        'data_points': len(sorted_vals),
    }
