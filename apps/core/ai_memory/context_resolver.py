"""
Context Snapshot Engine — Track what the user is currently viewing/doing.

Provides Priority 1 resolution: if the user says "the scripture" and they're
currently on a scripture page, we know which scripture they mean.
"""

from apps.core.ai_memory.models import ContextSnapshot


def store_context_snapshot(user, context_type, context_identifier, metadata=None):
    """
    Store or update the user's current context.

    Only keeps the most recent snapshot per context_type per user.
    Old snapshots remain for audit but the latest is always used.

    Args:
        user: Django user instance.
        context_type: Category (e.g., "scripture_page", "health_entry", "goal").
        context_identifier: Specific ID (e.g., "John 3", "weight_entry:123").
        metadata: Optional dict with additional context data.

    Returns:
        ContextSnapshot instance.
    """
    return ContextSnapshot.objects.create(
        user=user,
        context_type=context_type,
        context_identifier=context_identifier,
        metadata=metadata or {},
    )


def get_current_context(user, context_type):
    """
    Get the user's most recent context snapshot for a given type.

    Args:
        user: Django user instance.
        context_type: The type to look up (e.g., "scripture_page").

    Returns:
        ContextSnapshot instance or None.
    """
    return (
        ContextSnapshot.objects.filter(
            user=user,
            context_type=context_type,
        )
        .order_by("-created_at")
        .first()
    )


def get_all_current_contexts(user):
    """
    Get the latest context snapshot for each context_type.

    Returns a dict of context_type → ContextSnapshot.
    Useful for the orchestrator to check all active contexts at once.
    """
    # Get distinct context types, then latest for each
    context_types = (
        ContextSnapshot.objects.filter(user=user)
        .values_list("context_type", flat=True)
        .distinct()
    )

    contexts = {}
    for ct in context_types:
        snapshot = (
            ContextSnapshot.objects.filter(user=user, context_type=ct)
            .order_by("-created_at")
            .first()
        )
        if snapshot:
            contexts[ct] = snapshot

    return contexts


def clear_context(user, context_type):
    """
    Clear all context snapshots of a given type for a user.

    Used when the user navigates away from a page/section.
    """
    ContextSnapshot.objects.filter(
        user=user,
        context_type=context_type,
    ).delete()
