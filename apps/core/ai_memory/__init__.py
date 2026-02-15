"""
Self-Learning Context Memory Engine (SLCME)

Permanent learning layer for the AI Assistant. Learns from user clarification,
stores meanings, and reuses them automatically to improve accuracy over time.

Public API:
    resolve_context(user, phrase) -> tuple or None
    store_learned_mapping(user, phrase, meaning_type, meaning_identifier) -> LearnedMapping
    store_context_snapshot(user, context_type, context_identifier, metadata) -> ContextSnapshot
    log_clarification(user, original_input, question, response, resolved) -> ClarificationLog
"""

from apps.core.ai_memory.memory_engine import resolve_context
from apps.core.ai_memory.learning_engine import store_learned_mapping, log_clarification
from apps.core.ai_memory.context_resolver import store_context_snapshot, get_current_context

__all__ = [
    "resolve_context",
    "store_learned_mapping",
    "log_clarification",
    "store_context_snapshot",
    "get_current_context",
]
