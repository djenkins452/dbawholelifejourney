"""
SAE — State Updater.

Updates state incrementally after data changes. Called by the
UAIO execution engine after every successful action.

This is the function that activates the SAE hook in execution_engine.py:
    from apps.core.ai_state.state_updater import update_user_state
"""

import logging

from apps.core.ai_state.models import UserState
from apps.core.ai_state.state_builder import get_builder
from apps.core.ai_observability.instrumentation import log_engine_run as _instrument_engine_run

logger = logging.getLogger(__name__)


@_instrument_engine_run("SAE", 3)
def update_user_state(user, module, record_id=None):
    """
    Update state for a specific module after a data change.

    This is an incremental update — only rebuilds the affected module,
    not the entire state. Called automatically by UAIO after every
    successful action execution.

    Args:
        user: Django User instance.
        module: Module that changed (e.g., "health", "goals").
        record_id: Optional record ID for context (currently unused,
                   reserved for future delta updates).
    """
    # Resolve module to canonical name for state key
    canonical = _canonical_module(module)

    builder = get_builder(canonical)
    if builder is None:
        logger.debug(
            f"No state builder for module '{module}' (canonical: '{canonical}'). "
            f"Skipping state update for user {user.id}."
        )
        return

    try:
        # Build fresh state for this module
        module_state = builder(user)

        # Persist incrementally
        state_obj, created = UserState.objects.get_or_create(
            user=user, defaults={"state_data": {}}
        )

        state_data = state_obj.state_data or {}
        state_data[canonical] = module_state
        state_obj.state_data = state_data
        state_obj.save()

        logger.debug(
            f"SAE: Updated '{canonical}' state for user {user.id} "
            f"(record_id={record_id})"
        )

    except Exception as e:
        logger.error(
            f"SAE update failed for user {user.id}, module={module}: {e}",
            exc_info=True,
        )


def _canonical_module(module):
    """Map module aliases to canonical state keys."""
    aliases = {
        "purpose": "goals",
        "medical": "health",
        "labs": "health",
    }
    return aliases.get(module, module)
