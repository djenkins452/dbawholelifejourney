"""
Canonical Time Window Definitions — shared across all WLJ domains.

This module is the SINGLE SOURCE OF TRUTH for time-of-day window boundaries.
Used by: routines, medicine, meals, and any future scheduling system.

Do NOT define window logic elsewhere. Import from here.

Exports:
    WINDOW_HOURS           — {window_key: (start_h, end_h)}
    WINDOW_DISPLAY_NAMES   — {window_key: "Display Name"}
    WINDOW_ORDER           — [window_key, ...] in chronological order
    get_current_window(user) → str
    get_window_for_hour(hour) → str
    get_visibility_hours(window_key, buffer_hours=1) → (start_h, end_h)
    is_window_visible(window_key, current_hour, buffer_hours=1) → bool
    build_domain_time_context(user, items_by_window) → dict
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


# ── Visibility helpers ──────────────────────────────────────────────
# Used by dashboard and other UI layers that need to show/hide
# domain groups based on time proximity.


def get_visibility_hours(window_key, buffer_hours=1):
    """
    Return the visibility range for a window, with optional buffer.

    The buffer extends the start earlier and the end later, clamped to [0, 24].
    This allows UI layers to show groups slightly before they become active.

    Args:
        window_key: Canonical window key (e.g., 'morning').
        buffer_hours: Hours to extend visibility on each side (default 1).

    Returns:
        tuple: (start_h, end_h) — visibility range, inclusive start, exclusive end.
               Returns (0, 24) for unknown windows.
    """
    if window_key not in WINDOW_HOURS:
        return (0, 24)
    start_h, end_h = WINDOW_HOURS[window_key]
    return (max(0, start_h - buffer_hours), min(24, end_h + buffer_hours))


def is_window_visible(window_key, current_hour, buffer_hours=1):
    """
    Check if a window should be visible at the given hour.

    A window is visible when the current hour falls within its canonical
    range extended by the buffer.

    Args:
        window_key: Canonical window key.
        current_hour: User's current hour (0-23).
        buffer_hours: Visibility buffer (default 1).

    Returns:
        bool: True if window is visible at current_hour.
    """
    start_h, end_h = get_visibility_hours(window_key, buffer_hours)
    return start_h <= current_hour < end_h


# ── Shared time context structure ───────────────────────────────────
# Standard structure for any domain that groups items by time window.
# Used by routines, medicine, meals, and future domains.


def build_domain_time_context(user, items_by_window):
    """
    Build a standardized time context structure for a domain.

    This produces the canonical contract shape that ALL time-grouped
    domains should use. Domains provide their items_by_window dict;
    this function adds current_window, ordering, display names, and
    summary counts.

    Args:
        user: User instance (for timezone-aware current window).
        items_by_window: dict of {window_key: [item_dicts]}.
            Each item_dict MUST have a 'status' key with value
            'completed', 'pending', 'missed', 'skipped', or similar.

    Returns:
        dict: {
            'current_window': str,
            'windows': [
                {
                    'key': str,
                    'name': str,
                    'items': list,
                    'is_current': bool,
                    'completed_count': int,
                    'total_count': int,
                },
                ...
            ],
            'summary': {
                'total': int,
                'completed': int,
                'missed': int,
            },
        }
    """
    current_window = get_current_window(user)
    total = 0
    completed = 0
    missed = 0

    windows = []
    for key in WINDOW_ORDER:
        items = items_by_window.get(key, [])
        window_completed = sum(
            1 for i in items if i.get('status') in ('completed', 'taken')
        )
        window_missed = sum(
            1 for i in items if i.get('status') == 'missed'
        )
        total += len(items)
        completed += window_completed
        missed += window_missed

        windows.append({
            'key': key,
            'name': WINDOW_DISPLAY_NAMES.get(key, key.title()),
            'items': items,
            'is_current': key == current_window,
            'completed_count': window_completed,
            'total_count': len(items),
        })

    return {
        'current_window': current_window,
        'windows': windows,
        'summary': {
            'total': total,
            'completed': completed,
            'missed': missed,
        },
    }
