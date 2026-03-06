"""
SAE — State Engine.

Primary interface for reading user state. This is the standard
state retrieval interface used by all intelligence engines.

Performance target: < 10ms for cached state reads.
Full rebuilds hit the database and take longer.
"""

import logging

from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run
from apps.core.ai_state.models import UserState

logger = logging.getLogger(__name__)


def get_user_state(user):
    """
    Get the full state snapshot for a user.

    Returns the cached state_data dict. If no state exists yet,
    triggers a full rebuild.

    Supports per-request caching: if ``user._sae_cache`` is set
    (e.g. by ``build_cos_context``), returns it directly, avoiding
    repeated DB hits during the same request cycle.

    Args:
        user: Django User instance.

    Returns:
        dict — structured state snapshot keyed by module.
    """
    # Fast path: per-request cache set by build_cos_context
    cached = getattr(user, "_sae_cache", None)
    if cached is not None:
        return cached

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


@_instrument_engine_run("SAE", 1)
def rebuild_user_state(user):
    """
    Full rebuild of user state from database.

    This reads all domain data and produces a complete snapshot.
    Use sparingly — prefer incremental updates via state_updater.

    Modules are built and saved incrementally so that composite builders
    (like transformation) can read already-built module state from the DB.

    Args:
        user: Django User instance.

    Returns:
        dict — complete state snapshot.
    """
    from apps.core.ai_state.state_builder import get_all_builders

    state_obj, _ = UserState.objects.get_or_create(user=user)
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

        # Save incrementally so composite builders (e.g. transformation)
        # can read already-built modules from the database.
        state_obj.state_data = state
        state_obj.save()

    return state


def get_state_value(user, path, default=None):
    """
    Get a specific value from the user's state using dot-path notation.

    This is the preferred way to access individual state values without
    fetching the full state snapshot.

    Args:
        user: Django User instance.
        path: Dot-separated path (e.g., "health.weight_current",
              "goals.active_goal_count", "journal.days_since_entry").
        default: Value to return if path not found.

    Returns:
        The value at the given path, or default if not found.

    Examples:
        >>> get_state_value(user, "health.weight_current")
        180.5
        >>> get_state_value(user, "goals.active_goal_count", 0)
        3
        >>> get_state_value(user, "journal.last_mood", "")
        "great"
    """
    parts = path.split(".")
    if len(parts) < 2:
        return default

    module = parts[0]
    field_path = parts[1:]

    state = get_module_state(user, module)
    if not state:
        return default

    # Walk the nested path
    current = state
    for part in field_path:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default

    return current


def _canonical_module(module):
    """Map module aliases to canonical keys."""
    aliases = {
        "purpose": "goals",
        "medical": "health",
        "labs": "health",
        "food": "nutrition",
        "workout": "fitness",
        "workouts": "fitness",
        "training": "fitness",
    }
    return aliases.get(module, module)
