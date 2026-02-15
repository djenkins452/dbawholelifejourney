"""
SAE — State Awareness Engine.

Maintains an always-current snapshot of each user's life state.
This is the authoritative source of "current state" for the entire
intelligence system.

Public API:
    get_user_state(user) → dict            # Read full state
    get_module_state(user, module) → dict   # Read single module
    get_state_value(user, path, default)    # Read single value by dot-path
    update_user_state(user, module, record_id=None)  # Update after action
    rebuild_user_state(user) → dict         # Full rebuild
    get_cached_data(user, module, data_type, lookback_days) → QuerySet|list
"""

from apps.core.ai_state.state_engine import (  # noqa: F401
    get_module_state,
    get_state_value,
    get_user_state,
    rebuild_user_state,
)
from apps.core.ai_state.state_reader import get_cached_data  # noqa: F401
from apps.core.ai_state.state_updater import update_user_state  # noqa: F401
