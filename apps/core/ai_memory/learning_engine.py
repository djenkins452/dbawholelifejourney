"""
Learning Engine — Store new knowledge when user clarifies meaning.

Confidence starts at 0.8 for new mappings and grows by 0.05 per reuse,
capped at 1.0. This prevents premature overconfidence while rewarding
consistent usage.
"""

from apps.core.ai_memory.models import ClarificationLog, LearnedMapping
from apps.core.time.system_clock import get_current_time

# Initial confidence for a brand new mapping
INITIAL_CONFIDENCE = 0.8

# How much confidence grows per reuse
CONFIDENCE_INCREMENT = 0.05

# Maximum confidence score
MAX_CONFIDENCE = 1.0


# Meaning types allowed during Learning Mode (preference_only context).
# These are value/priority declarations — not execution-relevant mappings.
PREFERENCE_ONLY_ALLOWED_TYPES = frozenset({
    'sacred_activity',
    'core_people',
    'stated_value',
    'module_priority',
    'accountability_preference',
    'communication_frequency',
    'peak_productivity',
    'leisure_preference',
    'personal_time_preference',
    'negotiable_activity',
    'checkin_time_preference',
    'reconnection_target',
    'identity_statement',
    'motivational_trigger',
    'avoidance_pattern',
    'recurring_goal',
    'governance_preference',
    'calibration_response',
    'relationship_checkin',
})


def store_learned_mapping(
    user, phrase, meaning_type, meaning_identifier,
    confidence=None, learning_context=None,
):
    """
    Store or update a learned phrase→meaning mapping.

    If the exact phrase already exists for this user:
    - Increment usage_count
    - Boost confidence (up to MAX_CONFIDENCE)
    - Update last_used_at
    - Update meaning if different (reset confidence slightly)

    During Learning Mode (learning_context='preference_only'):
    - Only preference-based meaning types are stored at full confidence
    - Execution-relevant mappings are stored inactive with confidence=0.0
      (preserved for Phase 2 review, never auto-resolved into actions)

    Args:
        user: Django user instance.
        phrase: The user's phrase (e.g., "the scripture").
        meaning_type: Category (e.g., "scripture", "goal").
        meaning_identifier: Specific ID (e.g., "John 3:16", "goal:42").
        confidence: Optional override for initial confidence.
        learning_context: Optional context flag. 'preference_only' constrains
            which meaning types are stored actively.

    Returns:
        LearnedMapping instance (created or updated).
    """
    now = get_current_time()

    # Learning Mode constraint: execution-relevant mappings stored inactive
    store_inactive = False
    if learning_context == 'preference_only':
        if meaning_type not in PREFERENCE_ONLY_ALLOWED_TYPES:
            store_inactive = True

    # Determine initial confidence
    initial_conf = confidence if confidence is not None else INITIAL_CONFIDENCE
    if store_inactive:
        initial_conf = 0.0

    mapping, created = LearnedMapping.objects.get_or_create(
        user=user,
        phrase__iexact=phrase.strip(),
        is_active=not store_inactive,
        defaults={
            "phrase": phrase.strip(),
            "meaning_type": meaning_type,
            "meaning_identifier": meaning_identifier,
            "confidence_score": initial_conf,
            "usage_count": 1,
            "last_used_at": now,
        },
    )

    if not created:
        # Same meaning — reinforce (but not if being stored inactive)
        if store_inactive:
            return mapping

        if (
            mapping.meaning_type == meaning_type
            and mapping.meaning_identifier == meaning_identifier
        ):
            mapping.usage_count += 1
            mapping.confidence_score = min(
                mapping.confidence_score + CONFIDENCE_INCREMENT, MAX_CONFIDENCE
            )
        else:
            # Different meaning — user corrected. Update but lower confidence.
            mapping.meaning_type = meaning_type
            mapping.meaning_identifier = meaning_identifier
            mapping.confidence_score = initial_conf or INITIAL_CONFIDENCE
            mapping.usage_count = 1

        mapping.last_used_at = now
        mapping.save()

    return mapping


def record_usage(mapping):
    """
    Record that a mapping was used (without changing meaning).

    Called when the memory engine auto-resolves using a stored mapping.
    """
    mapping.usage_count += 1
    mapping.confidence_score = min(
        mapping.confidence_score + CONFIDENCE_INCREMENT, MAX_CONFIDENCE
    )
    mapping.last_used_at = get_current_time()
    mapping.save(update_fields=["usage_count", "confidence_score", "last_used_at"])


def deactivate_mapping(mapping):
    """
    Soft-deactivate a mapping (user explicitly corrects it permanently).
    """
    mapping.is_active = False
    mapping.save(update_fields=["is_active", "updated_at"])


def log_clarification(user, original_input, question, response, resolved, mapping=None):
    """
    Log a clarification exchange for audit purposes.

    Args:
        user: Django user instance.
        original_input: What the user originally said.
        question: What the AI asked.
        response: What the user responded.
        resolved: The final resolved meaning.
        mapping: Optional LearnedMapping created from this clarification.

    Returns:
        ClarificationLog instance.
    """
    return ClarificationLog.objects.create(
        user=user,
        original_input=original_input,
        clarification_question=question,
        user_response=response,
        resolved_meaning=resolved,
        learned_mapping=mapping,
    )
