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
