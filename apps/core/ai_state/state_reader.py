"""
SAE — State Reader.

Provides cached data access for prediction rules and insight rules.
This activates the SAE hook in prediction_engine.py:
    from apps.core.ai_state.state_reader import get_cached_data

Currently returns None for all data_types, causing the prediction
engine to fall back to direct database queries. This is intentional —
the state reader will be enhanced to return cached QuerySet-compatible
data as the SAE matures.

The state reader CAN provide scalar values from state_data for
performance-sensitive lookups that don't need full QuerySets.
"""

import logging

from apps.core.ai_state.state_engine import get_module_state

logger = logging.getLogger(__name__)


def get_cached_data(user, module, data_type, lookback_days=90):
    """
    Read cached data for predictions/insights.

    This is the SAE hook called by PRIE's get_prediction_input_data().

    Currently returns None for QuerySet-type data (predictions need
    raw data points for regression). Returns cached scalar values
    when available for quick lookups.

    Args:
        user: Django User instance.
        module: Module name (e.g., "health", "goals").
        data_type: Type of data (e.g., "weight_entries", "active_goals").
        lookback_days: Lookback window (unused for cached reads).

    Returns:
        Data if cached and available, None to trigger DB fallback.
    """
    # For QuerySet-type data (time-series for regression), fall back to DB.
    # The prediction engine needs raw data points, not summaries.
    queryset_types = {
        "weight_entries",
        "body_fat_entries",
        "lean_mass_entries",
        "lab_results",
    }
    if data_type in queryset_types:
        return None  # Fall back to database for time-series data

    # For scalar/summary data, we can use the cached state
    try:
        state = get_module_state(user, module)
        if not state:
            return None

        # Map data_type to cached state fields
        if data_type == "active_goals":
            # Only return from cache if state is populated
            if "active_goal_count" in state and state["active_goal_count"] > 0:
                # Can't return a QuerySet from cache — fall back
                return None

        if data_type == "active_habits":
            if "active_habit_count" in state and state["active_habit_count"] > 0:
                return None

    except Exception as e:
        logger.warning(f"SAE state read failed: {e}")

    return None  # Default: fall back to database
