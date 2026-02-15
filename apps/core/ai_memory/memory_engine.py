"""
Memory Engine Orchestrator — Main entry point for context resolution.

Resolution priority order:
1. Current context snapshot (what the user is looking at right now)
2. Learned mappings (past clarifications with sufficient confidence)
3. Return None → caller should do database lookup or ask user

This module NEVER guesses. If it can't resolve with confidence, it returns None.
"""

from apps.core.ai_memory.confidence_engine import (
    get_confidence_level,
    is_safe_to_use,
    needs_confirmation,
)
from apps.core.ai_memory.context_resolver import get_current_context
from apps.core.ai_memory.learning_engine import record_usage
from apps.core.ai_memory.retrieval_engine import find_learned_mapping


class MemoryResolution:
    """Result of a memory resolution attempt."""

    __slots__ = (
        "resolved",
        "meaning_type",
        "meaning_identifier",
        "source",
        "confidence",
        "needs_confirmation",
        "confirmation_question",
        "metadata",
    )

    def __init__(self, **kwargs):
        self.resolved = kwargs.get("resolved", False)
        self.meaning_type = kwargs.get("meaning_type")
        self.meaning_identifier = kwargs.get("meaning_identifier")
        self.source = kwargs.get("source")  # "context", "learned", None
        self.confidence = kwargs.get("confidence", "none")
        self.needs_confirmation = kwargs.get("needs_confirmation", False)
        self.confirmation_question = kwargs.get("confirmation_question")
        self.metadata = kwargs.get("metadata", {})

    def to_dict(self):
        result = {
            "resolved": self.resolved,
            "source": self.source,
            "confidence": self.confidence,
        }
        if self.resolved:
            result["meaning_type"] = self.meaning_type
            result["meaning_identifier"] = self.meaning_identifier
            if self.metadata:
                result["metadata"] = self.metadata
        if self.needs_confirmation:
            result["needs_confirmation"] = True
            result["confirmation_question"] = self.confirmation_question
        return result


def resolve_context(user, phrase, context_type_hint=None):
    """
    Attempt to resolve a phrase's meaning using memory.

    Resolution priority:
    1. Current context snapshot (if context_type_hint provided)
    2. Learned mappings (high confidence → auto-use)
    3. Learned mappings (medium confidence → suggest with confirmation)
    4. None → caller must ask user

    Args:
        user: Django user instance.
        phrase: The phrase to resolve (e.g., "the scripture").
        context_type_hint: Optional hint about what kind of context
                          to check (e.g., "scripture_page").

    Returns:
        MemoryResolution instance.
    """
    # Priority 1: Current context snapshot
    if context_type_hint:
        snapshot = get_current_context(user, context_type_hint)
        if snapshot:
            return MemoryResolution(
                resolved=True,
                meaning_type=snapshot.context_type,
                meaning_identifier=snapshot.context_identifier,
                source="context",
                confidence="high",
                metadata=snapshot.metadata,
            )

    # Priority 2: Learned mappings
    mapping = find_learned_mapping(user, phrase)

    if mapping:
        if is_safe_to_use(mapping):
            # High confidence — auto-use and record usage
            record_usage(mapping)
            return MemoryResolution(
                resolved=True,
                meaning_type=mapping.meaning_type,
                meaning_identifier=mapping.meaning_identifier,
                source="learned",
                confidence="high",
            )

        if needs_confirmation(mapping):
            # Medium confidence — suggest but ask for confirmation
            return MemoryResolution(
                resolved=False,
                meaning_type=mapping.meaning_type,
                meaning_identifier=mapping.meaning_identifier,
                source="learned",
                confidence="medium",
                needs_confirmation=True,
                confirmation_question=(
                    f'Did you mean "{mapping.meaning_identifier}" '
                    f"({mapping.meaning_type})?"
                ),
            )

    # Priority 3/4: Not resolved — caller must do DB lookup or ask user
    return MemoryResolution(resolved=False, source=None, confidence="none")
