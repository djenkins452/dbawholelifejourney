"""
Phase 10 — Schedule change weight calculation.

Deterministic weight + instability_points from time delta.
"""


def compute_schedule_change_weight(old_start, new_start):
    """
    Compute weight and instability_points for a schedule time change.

    Args:
        old_start: datetime — original start time (aware).
        new_start: datetime — new start time (aware).

    Returns:
        dict with 'weight', 'instability_points', 'delta_minutes',
        'date_changed'.
    """
    delta = abs((new_start - old_start).total_seconds()) / 60.0
    delta_minutes = int(delta)

    if delta_minutes < 15:
        weight = 5
        instability_points = 0
    elif delta_minutes < 60:
        weight = 20
        instability_points = 1
    elif delta_minutes < 180:
        weight = 45
        instability_points = 3
    else:
        weight = 75
        instability_points = 5

    date_changed = old_start.date() != new_start.date()
    if date_changed:
        weight = max(weight, 60)
        instability_points = max(instability_points, 4)

    return {
        'weight': weight,
        'instability_points': instability_points,
        'delta_minutes': delta_minutes,
        'date_changed': date_changed,
    }
