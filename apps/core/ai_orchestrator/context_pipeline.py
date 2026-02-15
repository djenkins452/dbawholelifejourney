"""
Context Pipeline — Integrates SLCME into the AI orchestration flow.

Resolves ambiguous references using learned mappings and current context.
"""

import logging

from apps.core.ai_memory.memory_engine import MemoryResolution, resolve_context
from apps.core.ai_memory.context_resolver import store_context_snapshot

logger = logging.getLogger(__name__)

# Map page module names to context types for snapshot storage
MODULE_TO_CONTEXT_TYPE = {
    "faith": "scripture_page",
    "health": "health_entry",
    "journal": "journal_entry",
    "purpose": "goal",
    "life": "task",
    "medical": "medical_record",
}


def resolve_context_pipeline(user, user_input, page_context=None):
    """
    Run the context resolution pipeline.

    1. Store current page context as a snapshot (if provided)
    2. Attempt to resolve any ambiguous references in user input

    Args:
        user: Django user instance.
        user_input: Raw user message string.
        page_context: Optional dict with 'url', 'module', 'page_title', etc.

    Returns:
        MemoryResolution instance (may be resolved, need confirmation, or unresolved).
    """
    try:
        # Step 1: Store page context as snapshot
        if page_context:
            _store_page_context(user, page_context)

        # Step 2: Resolve context
        # Determine context type hint from page context
        context_type_hint = None
        if page_context and page_context.get("module"):
            context_type_hint = MODULE_TO_CONTEXT_TYPE.get(
                page_context["module"]
            )

        resolution = resolve_context(
            user, user_input, context_type_hint=context_type_hint
        )

        return resolution

    except Exception as e:
        logger.error(f"Context pipeline error: {e}", exc_info=True)
        return MemoryResolution(resolved=False, source=None, confidence="none")


def _store_page_context(user, page_context):
    """Store the user's current page as a context snapshot."""
    module = page_context.get("module", "unknown")
    context_type = MODULE_TO_CONTEXT_TYPE.get(module, module)
    identifier = page_context.get("url", "")
    metadata = {
        "page_title": page_context.get("page_title", ""),
        "url": page_context.get("url", ""),
        "module": module,
    }

    try:
        store_context_snapshot(user, context_type, identifier, metadata)
    except Exception as e:
        logger.warning(f"Failed to store page context: {e}")
