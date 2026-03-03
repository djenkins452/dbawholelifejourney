"""
Safety Engine — Prevent hallucinated, invalid, or unsafe actions.

Validates actions before execution. Requires clarification if uncertain.
"""

import logging
import re
from datetime import timedelta

from apps.core.time.system_clock import get_current_time

logger = logging.getLogger(__name__)

# Maximum days in the past we'll accept for backdated entries
MAX_BACKDATE_DAYS = 365

# Maximum days in the future for scheduled actions
MAX_FUTURE_DAYS = 365

# Words that explicitly signal delete intent (case-insensitive)
_DELETE_VERBS = re.compile(
    r'\b(delete|remove|cancel|get rid of|trash|erase)\b',
    re.IGNORECASE,
)


class SafetyResult:
    """Result of safety validation."""

    __slots__ = ("is_safe", "reason", "user_message")

    def __init__(self, is_safe=True, reason=None, user_message=None):
        self.is_safe = is_safe
        self.reason = reason
        self.user_message = user_message or ""


def validate_action(enriched_action):
    """
    Validate an action before execution.

    Checks:
    - Resolved timestamps are within reasonable bounds
    - Required parameters are present
    - No obviously invalid values
    - Delete actions require explicit delete language in user message

    Args:
        enriched_action: EnrichedAction from action_router.

    Returns:
        SafetyResult (is_safe=True if OK to proceed).
    """
    params = enriched_action.parameters

    # ── Delete-intent verification ────────────────────────────
    # Block task deletion unless the user's original message contains
    # an explicit delete verb. Prevents the AI from interpreting
    # "don't show those" or "hide completed" as "delete".
    if (enriched_action.intent_type == 'mutate_task'
            and params.get('action') == 'delete'):
        original = enriched_action.original_input or ''
        if not _DELETE_VERBS.search(original):
            logger.warning(
                "Delete-intent blocked: user said %r but no explicit delete verb found",
                original[:200],
            )
            return SafetyResult(
                is_safe=False,
                reason="delete_not_explicit",
                user_message=(
                    "I wasn't sure if you wanted to delete those tasks. "
                    "If you'd like to remove a task, just say "
                    "\"delete [task name]\" and I'll take care of it."
                ),
            )

    # Check timestamp bounds if time was resolved
    if params.get("_time_resolved") and "recorded_at" in params:
        recorded_at = params["recorded_at"]
        now = get_current_time()

        # Check if too far in the past
        max_past = now - timedelta(days=MAX_BACKDATE_DAYS)
        if recorded_at < max_past:
            return SafetyResult(
                is_safe=False,
                reason="timestamp_too_old",
                user_message=(
                    f"That date is more than {MAX_BACKDATE_DAYS} days ago. "
                    "Could you double-check the date?"
                ),
            )

        # Check if too far in the future (for non-scheduling intents)
        scheduling_intents = {"create_event", "add_reminder", "create_appointment", "mutate_calendar_event"}
        if enriched_action.intent_type not in scheduling_intents:
            if recorded_at > now + timedelta(hours=1):
                return SafetyResult(
                    is_safe=False,
                    reason="future_timestamp_for_log",
                    user_message=(
                        "That time is in the future. Did you mean to log "
                        "something for a past date instead?"
                    ),
                )

        # Scheduling intents: check not too far in future
        max_future = now + timedelta(days=MAX_FUTURE_DAYS)
        if recorded_at > max_future:
            return SafetyResult(
                is_safe=False,
                reason="timestamp_too_future",
                user_message=(
                    f"That date is more than {MAX_FUTURE_DAYS} days in the future. "
                    "Could you double-check?"
                ),
            )

    return SafetyResult(is_safe=True)
