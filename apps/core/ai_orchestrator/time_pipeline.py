"""
Time Pipeline — Integrates HTIE into the AI orchestration flow.

Resolves natural language time expressions in user input into
precise timestamps for action handlers.
"""

import logging

from apps.core.time.interpreter import InterpretationResult, interpret_human_time

logger = logging.getLogger(__name__)


def resolve_time_pipeline(user_input, user_timezone=None):
    """
    Run the time resolution pipeline on user input.

    Args:
        user_input: Raw user message string.
        user_timezone: Optional IANA timezone string.

    Returns:
        InterpretationResult from HTIE (may have resolved time,
        need clarification, or have no time expression).
    """
    try:
        result = interpret_human_time(user_input, user_timezone=user_timezone)
        return result
    except Exception as e:
        logger.error(f"Time pipeline error: {e}", exc_info=True)
        return InterpretationResult(
            success=False,
            original_input=user_input,
            error=f"Time resolution error: {str(e)}",
        )


def enrich_parameters_with_time(parameters, time_result):
    """
    Enrich intent parameters with a resolved timestamp.

    If HTIE successfully resolved a time expression, add the resolved
    datetime as 'recorded_at' in the parameters dict. This overrides
    the default "now" timestamp used by action handlers.

    Args:
        parameters: Dict of intent parameters (e.g., {'value': 250, 'unit': 'lb'}).
        time_result: InterpretationResult from resolve_time_pipeline().

    Returns:
        Updated parameters dict (mutated in place and returned).
    """
    if (
        time_result
        and time_result.success
        and time_result.resolved_time
    ):
        parameters["recorded_at"] = time_result.resolved_time.datetime_aware
        parameters["_time_expression"] = time_result.time_expression
        parameters["_time_resolved"] = True

    return parameters


def get_user_timezone(user):
    """
    Get the user's configured timezone.

    Args:
        user: Django user instance.

    Returns:
        IANA timezone string (e.g., 'America/New_York'), or None.
    """
    try:
        prefs = getattr(user, "preferences", None)
        if prefs:
            return getattr(prefs, "timezone_iana", None) or getattr(
                prefs, "timezone", None
            )
    except Exception:
        pass
    return None
