"""
Structured message builder for OpenAI conversation threading.

Converts AssistantMessage querysets into properly structured
OpenAI message arrays for natural conversation threading.
"""

import logging
from typing import List, Dict, Optional

from .token_budget import trim_messages_to_token_budget

logger = logging.getLogger(__name__)

# Maximum characters per message content before truncation.
# Long assistant responses (data dumps, briefings) are trimmed to keep
# token costs reasonable while preserving conversational context.
MAX_CONTENT_CHARS = 800

# Maximum number of history messages to include (before token trimming).
# More recent messages are prioritized. 20 turns = ~10 exchanges.
MAX_HISTORY_MESSAGES = 20

# Token budget for the history portion of the message array.
# This leaves room for the system prompt and final user message.
HISTORY_TOKEN_BUDGET = 6000


def build_messages_from_history(
    history,
    current_user_input: str,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_content_chars: int = MAX_CONTENT_CHARS,
    token_budget: int = HISTORY_TOKEN_BUDGET,
) -> Optional[List[Dict]]:
    """Build a structured OpenAI message array from conversation history.

    Converts an AssistantMessage queryset (ordered newest-first) into
    a list of {"role": "user"|"assistant", "content": "..."} dicts
    suitable for insertion into the OpenAI messages array.

    The returned list does NOT include the system prompt or the final
    user message — those are added by the caller. The list represents
    the conversation history between system and the new user input.

    Args:
        history: QuerySet of AssistantMessage, ordered by -created_at.
                 Each must have .role ('user'|'assistant') and .content.
        current_user_input: The user's current message (used for dedup).
        max_messages: Maximum number of history messages to include.
        max_content_chars: Truncate individual messages beyond this length.
        token_budget: Maximum estimated tokens for the history portion.

    Returns:
        List of message dicts, or None if history is empty.
        Messages are in chronological order (oldest first).
    """
    if not history:
        return None

    # Take the N most recent and reverse to chronological order
    recent = list(history[:max_messages])
    recent.reverse()  # Now oldest-first

    messages = []
    for msg in recent:
        role = "user" if msg.role == "user" else "assistant"
        content = msg.content or ""

        # Skip empty messages
        if not content.strip():
            continue

        # Skip if this is a duplicate of the current input
        # (the current message may already be saved before we build history)
        if role == "user" and content.strip() == current_user_input.strip():
            # Only skip the LAST user message if it matches
            # (earlier identical messages are kept for context)
            if msg == recent[-1]:
                continue

        # Truncate long messages to keep context manageable
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "..."

        messages.append({"role": role, "content": content})

    if not messages:
        return None

    # Ensure message array starts with a user message for valid OpenAI format.
    # If it starts with assistant, drop leading assistant messages.
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)

    if not messages:
        return None

    # Wrap in dummy system/user for trimming, then unwrap
    # trim_messages_to_token_budget expects [system, ...history..., user]
    dummy_system = {"role": "system", "content": ""}
    dummy_user = {"role": "user", "content": current_user_input}
    full = [dummy_system] + messages + [dummy_user]
    trimmed = trim_messages_to_token_budget(full, max_tokens=token_budget)

    # Unwrap: remove dummy system and dummy user
    result = trimmed[1:-1]

    if result:
        logger.debug(
            "Built structured history: %d messages from %d available",
            len(result), len(recent),
        )

    return result if result else None
