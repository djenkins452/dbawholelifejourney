"""
Canonical Time Window Definitions — shared across all WLJ domains.

This module is the SINGLE SOURCE OF TRUTH for time-of-day window boundaries.
Used by: routines, medicine, meals, and any future scheduling system.

Do NOT define window logic elsewhere. Import from here.
"""

from apps.core.utils import get_user_now

# Hour ranges: inclusive start, exclusive end
WINDOW_HOURS = {
    'morning': (5, 10),
    'mid_morning': (10, 12),
    'lunch': (12, 14),
    'afternoon': (14, 17),
    'evening': (17, 21),
    'nightly': (21, 24),
}

WINDOW_DISPLAY_NAMES = {
    'morning': 'Morning',
    'mid_morning': 'Mid-Morning',
    'lunch': 'Lunch',
    'afternoon': 'Afternoon',
    'evening': 'Evening',
    'nightly': 'Nightly',
}

# Canonical ordering for consistent UI display
WINDOW_ORDER = ['morning', 'mid_morning', 'lunch', 'afternoon', 'evening', 'nightly']


def get_current_window(user):
    """
    Determine the current time window based on the user's local time.

    Returns:
        str: Window key (e.g., 'morning', 'afternoon') or 'other' if outside all windows.
    """
    user_now = get_user_now(user)
    return get_window_for_hour(user_now.time().hour)


def get_window_for_hour(hour):
    """
    Map an hour (0-23) to its canonical time window.

    Returns:
        str: Window key or 'other'.
    """
    for window_name, (start_h, end_h) in WINDOW_HOURS.items():
        if start_h <= hour < end_h:
            return window_name
    return 'other'
