"""
SAE — State Utilities.

Helper functions for state inspection and debugging.
"""

import logging

from apps.core.ai_state.models import UserState

logger = logging.getLogger(__name__)


def get_state_age_seconds(user):
    """
    Get how old the current state snapshot is, in seconds.

    Returns:
        float — seconds since last update, or None if no state exists.
    """
    from apps.core.time.system_clock import get_current_time

    try:
        state_obj = UserState.objects.filter(user=user).first()
        if state_obj and state_obj.last_updated:
            delta = get_current_time() - state_obj.last_updated
            return delta.total_seconds()
    except Exception:
        pass

    return None


def get_state_summary(user):
    """
    Get a human-readable summary of the user's state.

    Returns:
        dict with module names and key metrics.
    """
    from apps.core.ai_state.state_engine import get_user_state

    state = get_user_state(user)
    summary = {}

    for module, data in state.items():
        if isinstance(data, dict):
            summary[module] = {
                "fields": len(data),
                "keys": list(data.keys()),
            }

    return summary


def invalidate_state(user, module=None):
    """
    Invalidate cached state, forcing a rebuild on next access.

    Args:
        user: Django User instance.
        module: Optional module to invalidate. If None, clears everything.
    """
    try:
        state_obj = UserState.objects.filter(user=user).first()
        if not state_obj:
            return

        if module:
            # Remove just one module
            if module in state_obj.state_data:
                del state_obj.state_data[module]
                state_obj.save()
        else:
            # Clear all state
            state_obj.state_data = {}
            state_obj.save()
    except Exception as e:
        logger.error(f"State invalidation failed for user {user.id}: {e}")
