"""
SAE — State Engine.

Primary interface for reading user state. This is the standard
state retrieval interface used by all intelligence engines.

Performance target: < 10ms for cached state reads.
Full rebuilds hit the database and take longer.
"""

import logging

from apps.core.ai_state.models import UserState

logger = logging.getLogger(__name__)


def get_user_state(user):
    """
    Get the full state snapshot for a user.

    Returns the cached state_data dict. If no state exists yet,
    triggers a full rebuild.

    Args:
        user: Django User instance.

    Returns:
        dict — structured state snapshot keyed by module.
    """
    state_obj, created = UserState.objects.get_or_create(
        user=user, defaults={"state_data": {}}
    )

    if created or not state_obj.state_data:
        # First access — build full state
        return rebuild_user_state(user)

    return state_obj.state_data


def get_module_state(user, module):
    """
    Get state data for a specific module.

    Args:
        user: Django User instance.
        module: Module name (e.g., "health", "goals").

    Returns:
        dict — module-specific state data, or empty dict.
    """
    state = get_user_state(user)
    # Resolve aliases
    canonical = _canonical_module(module)
    return state.get(canonical, {})


def rebuild_user_state(user):
    """
    Full rebuild of user state from database.

    This reads all domain data and produces a complete snapshot.
    Use sparingly — prefer incremental updates via state_updater.

    Args:
        user: Django User instance.

    Returns:
        dict — complete state snapshot.
    """
    from apps.core.ai_state.state_builder import get_all_builders

    state = {}
    for module, builder in get_all_builders().items():
        try:
            state[module] = builder(user)
        except Exception as e:
            logger.error(
                f"State builder failed for user {user.id}, module={module}: {e}",
                exc_info=True,
            )
            state[module] = {}

    # Persist
    state_obj, _ = UserState.objects.get_or_create(user=user)
    state_obj.state_data = state
    state_obj.save()

    return state


def _canonical_module(module):
    """Map module aliases to canonical keys."""
    aliases = {
        "purpose": "goals",
        "medical": "health",
        "labs": "health",
    }
    return aliases.get(module, module)
