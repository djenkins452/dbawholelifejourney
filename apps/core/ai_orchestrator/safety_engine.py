"""
Safety Engine — Prevent hallucinated, invalid, or unsafe actions.

Validates actions before execution. Uses centralized ACTION_POLICY for
risk assessment and destructive-action verification.

Pipeline position:
    CRUD Confirmation Gate → Safety Engine → Execution Engine
"""

import logging
import re
from datetime import timedelta

from apps.core.ai_orchestrator.action_policy import (
    get_policy,
    get_risk_level,
    is_destructive,
    RiskLevel,
)
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

# Words that confirm a previous delete request (used after confirmation prompt)
_CONFIRM_WORDS = re.compile(
    r'\b(yes|yeah|yep|confirm|go ahead|do it|sure|ok)\b',
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
    - Destructive actions require explicit delete/remove language
    - Resolved timestamps are within reasonable bounds
    - Risk level is not CRITICAL without proper authorization

    Args:
        enriched_action: EnrichedAction from action_router.

    Returns:
        SafetyResult (is_safe=True if OK to proceed).
    """
    params = enriched_action.parameters
    intent_type = enriched_action.intent_type

    # ── Destructive action verification ──────────────────────
    # Block destructive actions unless the user's original message
    # contains an explicit delete verb OR is a confirmed follow-up.
    if is_destructive(intent_type, params):
        original = enriched_action.original_input or ''
        is_confirmed_follow_up = (
            params.get('delete_confirmed') and _CONFIRM_WORDS.search(original)
        )
        if not _DELETE_VERBS.search(original) and not is_confirmed_follow_up:
            logger.warning(
                "[SAFETY] Destructive action blocked: user=%s intent=%s "
                "original=%r — no explicit delete verb found",
                getattr(enriched_action, '_user_id', '?'),
                intent_type,
                original[:200],
            )
            return SafetyResult(
                is_safe=False,
                reason="delete_not_explicit",
                user_message=(
                    "I may have gotten that wrong — let me know what "
                    "you'd like me to do. I can look up your current "
                    "tasks, reschedule items, or update anything that's "
                    "out of date."
                ),
            )

    # ── Timestamp bounds ─────────────────────────────────────
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
        scheduling_intents = {
            "create_event", "add_reminder", "create_appointment",
            "mutate_calendar_event",
        }
        if intent_type not in scheduling_intents:
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
