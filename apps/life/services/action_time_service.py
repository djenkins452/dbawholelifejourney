"""
Action → Time Block Service

Assigns prioritized actions to suggested time windows within the
user's day. Answers "when should I do it?" — not "what should I do?"

Architecture: service layer only, no models, no DB writes, no calendar
events. Uses existing time windows from apps.core.time_windows.

Output is directional guidance for CoS, not a rigid schedule.
"""

import logging

logger = logging.getLogger(__name__)

# Duration heuristics by action type (minutes)
_DURATION_MAP = {
    'perform_maintenance': 45,
    'reset_routine': 20,
    'stabilize_routine': 15,
    'slow_down': 10,
}

# Window preference by priority — which windows to try first
_WINDOW_PREFERENCE = {
    'high': ['morning', 'mid_morning', 'lunch', 'afternoon'],
    'medium': ['afternoon', 'mid_morning', 'lunch', 'evening'],
    'low': ['evening', 'afternoon', 'nightly'],
}

# Window display labels for human-readable output
_WINDOW_LABELS = {
    'morning': 'this morning',
    'mid_morning': 'mid-morning',
    'lunch': 'around lunch',
    'afternoon': 'this afternoon',
    'evening': 'this evening',
    'nightly': 'tonight',
}

# Hour ranges matching apps.core.time_windows.WINDOW_HOURS
_WINDOW_HOURS = {
    'morning': (5, 10),
    'mid_morning': (10, 12),
    'lunch': (12, 14),
    'afternoon': (14, 17),
    'evening': (17, 21),
    'nightly': (21, 24),
}


def assign_time_blocks(actions, current_hour=None):
    """
    Assign suggested time blocks to prioritized actions.

    Args:
        actions: list[dict] — from generate_routine_actions()
            Each has: schedule_id, schedule_name, priority, action, message
        current_hour: int (0-23) — user's local hour. If None, all
            windows are considered available.

    Returns:
        list[dict] — same actions with added fields:
            - time_block: str (window key)
            - time_label: str (human-readable, e.g. "this afternoon")
            - suggested_duration: int (minutes)
            - guidance: str (CoS-ready sentence)
    """
    if not actions:
        return []

    # Track which windows are already assigned to avoid stacking
    _used_windows = set()
    result = []

    for action in actions:
        priority = action.get('priority', 'medium')
        action_type = action.get('action', '')

        # Get preferred windows for this priority
        preferred = _WINDOW_PREFERENCE.get(priority, ['afternoon'])

        # Find first available window that hasn't passed
        assigned_window = None
        for window in preferred:
            if window in _used_windows:
                continue
            # Skip windows that have already passed today
            if current_hour is not None:
                start_h, end_h = _WINDOW_HOURS.get(window, (0, 24))
                if current_hour >= end_h:
                    continue
            assigned_window = window
            break

        # Fallback: if all preferred windows are taken/passed, use any available
        if not assigned_window:
            from apps.core.time_windows import WINDOW_ORDER
            for window in WINDOW_ORDER:
                if window in _used_windows:
                    continue
                if current_hour is not None:
                    start_h, end_h = _WINDOW_HOURS.get(window, (0, 24))
                    if current_hour >= end_h:
                        continue
                assigned_window = window
                break

        if not assigned_window:
            # All windows passed or taken — defer to tomorrow
            assigned_window = 'morning'
            time_label = 'tomorrow morning'
        else:
            time_label = _WINDOW_LABELS.get(assigned_window, assigned_window)
            _used_windows.add(assigned_window)

        duration = _DURATION_MAP.get(action_type, 30)
        name = action.get('schedule_name', 'this')

        # Build CoS-ready guidance sentence
        guidance = f"Take {duration} minutes {time_label} to handle {name}."

        result.append({
            **action,
            'time_block': assigned_window,
            'time_label': time_label,
            'suggested_duration': duration,
            'guidance': guidance,
        })

    return result


def get_timed_actions_for_user(user):
    """
    Full pipeline: signals → actions → time blocks for a user.

    Args:
        user: Django User instance

    Returns:
        list[dict] — up to 3 time-blocked action recommendations
    """
    from apps.life.services.routine_action_service import get_routine_actions_for_user
    from apps.core.utils import get_user_now

    actions = get_routine_actions_for_user(user)
    if not actions:
        return []

    user_now = get_user_now(user)
    current_hour = user_now.hour

    return assign_time_blocks(actions, current_hour=current_hour)
