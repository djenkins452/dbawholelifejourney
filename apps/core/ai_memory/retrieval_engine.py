"""
Memory Retrieval Engine — Search learned mappings before asking the user.

Priority: exact match > case-insensitive match > fuzzy match.
Performance target: <50ms lookup.
"""

from django.db.models import Q

from apps.core.ai_memory.models import LearnedMapping


def find_learned_mapping(user, phrase):
    """
    Find the best learned mapping for a phrase.

    Searches active mappings ordered by confidence and usage.
    Returns the highest-confidence match, or None.

    Args:
        user: The Django user instance.
        phrase: The phrase to look up (e.g., "the scripture").

    Returns:
        LearnedMapping instance or None.
    """
    if not phrase or not phrase.strip():
        return None

    clean_phrase = phrase.strip()

    # Exact case-insensitive match (most common, fastest)
    mapping = (
        LearnedMapping.objects.filter(
            user=user,
            phrase__iexact=clean_phrase,
            is_active=True,
        )
        .order_by("-confidence_score", "-usage_count")
        .first()
    )

    return mapping


def find_mappings_by_type(user, meaning_type):
    """
    Find all learned mappings of a given type for a user.

    Useful for listing all learned scripture references, goals, etc.

    Args:
        user: The Django user instance.
        meaning_type: The type to filter by (e.g., "scripture", "goal").

    Returns:
        QuerySet of LearnedMapping instances.
    """
    return LearnedMapping.objects.filter(
        user=user,
        meaning_type=meaning_type,
        is_active=True,
    ).order_by("-confidence_score", "-usage_count")


def find_similar_mappings(user, phrase, limit=5):
    """
    Find mappings with similar phrases (contains match).

    Used as a fallback when exact match fails. Returns candidates
    the orchestrator can evaluate.

    Args:
        user: The Django user instance.
        phrase: The phrase to search for.
        limit: Max number of results.

    Returns:
        QuerySet of LearnedMapping instances.
    """
    if not phrase or not phrase.strip():
        return LearnedMapping.objects.none()

    clean_phrase = phrase.strip()

    return (
        LearnedMapping.objects.filter(
            user=user,
            is_active=True,
        )
        .filter(
            Q(phrase__icontains=clean_phrase)
            | Q(meaning_identifier__icontains=clean_phrase)
        )
        .order_by("-confidence_score", "-usage_count")[:limit]
    )
