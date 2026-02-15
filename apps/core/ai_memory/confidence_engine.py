"""
Confidence Engine — Determine whether a learned mapping is safe to auto-use.

A mapping must meet the confidence threshold before the AI can use it
without asking the user for confirmation. This prevents premature
assumptions from low-confidence or rarely-used mappings.
"""

# Minimum confidence score required to auto-use a mapping
CONFIDENCE_THRESHOLD = 0.75

# Minimum usage count to consider a mapping established
MIN_USAGE_FOR_AUTO = 1

# Confidence below which a mapping should be confirmed with user
CONFIRMATION_THRESHOLD = 0.5


def is_safe_to_use(mapping):
    """
    Check if a mapping has sufficient confidence to use automatically.

    Args:
        mapping: LearnedMapping instance.

    Returns:
        True if the mapping can be used without confirmation.
    """
    if not mapping or not mapping.is_active:
        return False

    return (
        mapping.confidence_score >= CONFIDENCE_THRESHOLD
        and mapping.usage_count >= MIN_USAGE_FOR_AUTO
    )


def needs_confirmation(mapping):
    """
    Check if a mapping exists but needs user confirmation before use.

    This is the middle ground: we found something relevant but aren't
    confident enough to use it silently.

    Args:
        mapping: LearnedMapping instance.

    Returns:
        True if we should ask "Did you mean X?" instead of assuming.
    """
    if not mapping or not mapping.is_active:
        return False

    return (
        CONFIRMATION_THRESHOLD <= mapping.confidence_score < CONFIDENCE_THRESHOLD
    )


def get_confidence_level(mapping):
    """
    Get a human-readable confidence level for a mapping.

    Returns:
        "high" (auto-use), "medium" (confirm), "low" (ignore), or "none".
    """
    if not mapping or not mapping.is_active:
        return "none"

    if mapping.confidence_score >= CONFIDENCE_THRESHOLD:
        return "high"
    elif mapping.confidence_score >= CONFIRMATION_THRESHOLD:
        return "medium"
    else:
        return "low"
