"""
Conversation threading sub-package.

Provides structured conversation threading utilities:
- message_builder: Build OpenAI message arrays from conversation history
- token_budget: Token estimation and history trimming
"""

from .message_builder import build_messages_from_history
from .token_budget import trim_messages_to_token_budget

__all__ = [
    'build_messages_from_history',
    'trim_messages_to_token_budget',
]
