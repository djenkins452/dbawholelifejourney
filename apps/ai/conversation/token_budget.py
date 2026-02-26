"""
Token budget management for conversation history.

Estimates token counts and trims message arrays to stay within
the context window budget, preserving the most recent messages.
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# Average chars per token for English text (conservative estimate).
# GPT-family models average ~4 chars/token; we use 3.5 to be safe.
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Estimate token count for a string using char-ratio heuristic."""
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN) + 1


def estimate_message_tokens(message: Dict) -> int:
    """Estimate tokens for a single OpenAI message dict.

    Accounts for role overhead (~4 tokens per message for role/delimiters).
    """
    content = message.get("content", "")
    if isinstance(content, list):
        # Vision messages with image_url blocks — only count text parts
        text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
        content = " ".join(text_parts)
    return estimate_tokens(content) + 4  # role + delimiter overhead


def trim_messages_to_token_budget(
    messages: List[Dict],
    max_tokens: int = 6000,
) -> List[Dict]:
    """Trim a conversation history message list to fit within a token budget.

    Strategy:
    - Always keep the most recent messages (they're most relevant)
    - Drop oldest messages first when over budget
    - Never drop the system message (index 0) or the final user message

    Args:
        messages: Full message list [system, ...history..., user]
        max_tokens: Maximum token budget for the history portion.
                    This is ONLY for the conversation history messages,
                    NOT the system prompt or final user message.

    Returns:
        Trimmed message list maintaining [system, ...history..., user] structure.
    """
    if len(messages) <= 2:
        # Just system + user, no history to trim
        return messages

    system_msg = messages[0]
    final_user_msg = messages[-1]
    history = messages[1:-1]  # Everything between system and final user

    if not history:
        return messages

    # Calculate total history tokens
    total_tokens = sum(estimate_message_tokens(m) for m in history)

    if total_tokens <= max_tokens:
        return messages  # Fits within budget

    # Trim from the oldest (front) until we fit
    trimmed = list(history)
    while trimmed and total_tokens > max_tokens:
        removed = trimmed.pop(0)
        total_tokens -= estimate_message_tokens(removed)

    logger.debug(
        "Trimmed conversation history: %d → %d messages, ~%d tokens",
        len(history), len(trimmed), total_tokens,
    )

    return [system_msg] + trimmed + [final_user_msg]
