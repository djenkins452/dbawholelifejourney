"""
Phase 4 CoS — Learning Extractor.

After every assistant interaction, extracts:
- Stated values
- Repeated frustrations
- Recurring goals
- Non-negotiables
- Relationship priorities
- Identity statements
- Motivational triggers
- Avoidance patterns

Stores in UserLearnedProfile (user-visible, editable).
Injected into assistant system prompt on next interaction.

Public API:
    - extract_learning(user, user_message, assistant_response) -> list[LearningExtraction]
    - get_learned_profile(user) -> UserLearnedProfile
    - get_profile_system_prompt(user) -> str
    - remove_learned_item(user, category, text) -> bool
"""

import logging
import re

from django.utils import timezone

from apps.core.ai_learning.models import LearningExtraction, UserLearnedProfile

logger = logging.getLogger(__name__)

# Keyword patterns for extraction (lightweight, no AI call needed)
EXTRACTION_PATTERNS = {
    "stated_value": [
        r"(?:I (?:really )?(?:value|believe in|care about|prioritize))\s+(.+?)(?:\.|,|$)",
        r"(?:what matters (?:most )?(?:to me|is))\s+(.+?)(?:\.|,|$)",
        r"(?:my (?:core )?values? (?:is|are|include))\s+(.+?)(?:\.|,|$)",
    ],
    "non_negotiable": [
        r"(?:I (?:will )?never (?:skip|miss|compromise on|give up))\s+(.+?)(?:\.|,|$)",
        r"(?:(?:that's|this is|it's) non[- ]negotiable)\b",
        r"(?:I (?:always|must) (?:do|have|keep))\s+(.+?)(?:\.|,|$)",
    ],
    "identity_statement": [
        r"(?:I am (?:a |an )?)([\w\s]+?)(?:\.|,|$)",
        r"(?:I'm (?:a |an )?)([\w\s]+?)(?:\.|,|$)",
        r"(?:I see myself as)\s+(.+?)(?:\.|,|$)",
    ],
    "frustration": [
        r"(?:I'm (?:frustrated|annoyed|tired|sick) (?:of|with|by))\s+(.+?)(?:\.|,|$)",
        r"(?:(?:it |that )(?:frustrates|annoys|bothers) me)\s*(.+?)(?:\.|,|$)",
        r"(?:I (?:keep|always) (?:struggling|failing) (?:with|at|to))\s+(.+?)(?:\.|,|$)",
    ],
    "recurring_goal": [
        r"(?:I (?:want|need|plan|aim) to)\s+(.+?)(?:\.|,|$)",
        r"(?:my goal is to)\s+(.+?)(?:\.|,|$)",
        r"(?:I'm (?:working|trying) (?:on|to))\s+(.+?)(?:\.|,|$)",
    ],
    "relationship_priority": [
        r"(?:my (?:wife|husband|spouse|partner|kids?|children|family|mom|dad|friend))\s",
        r"(?:(?:spending|quality) time with)\s+(.+?)(?:\.|,|$)",
        r"(?:I need to (?:be there for|connect with|call|visit))\s+(.+?)(?:\.|,|$)",
    ],
    "motivational_trigger": [
        r"(?:(?:that|this|it) (?:motivates|inspires|energizes|fires) me)\b",
        r"(?:I (?:feel|get) (?:motivated|energized|inspired) (?:when|by))\s+(.+?)(?:\.|,|$)",
        r"(?:what (?:drives|pushes|motivates) me is)\s+(.+?)(?:\.|,|$)",
    ],
    "avoidance_pattern": [
        r"(?:I (?:don't want|refuse|avoid|hate) to)\s+(.+?)(?:\.|,|$)",
        r"(?:I (?:keep )?(?:avoiding|putting off|procrastinating))\s+(.+?)(?:\.|,|$)",
    ],
}

# Category → profile field mapping
CATEGORY_FIELD_MAP = {
    "stated_value": "stated_values",
    "frustration": "repeated_frustrations",
    "recurring_goal": "recurring_goals",
    "non_negotiable": "non_negotiables",
    "relationship_priority": "relationship_priorities",
    "identity_statement": "identity_statements",
    "motivational_trigger": "motivational_triggers",
    "avoidance_pattern": "avoidance_patterns",
}

# Max items per category
MAX_ITEMS_PER_CATEGORY = 15


def extract_learning(user, user_message, assistant_response=None):
    """
    Extract learning from a user message.

    Runs lightweight pattern matching — no AI call needed.
    Only stores high-confidence, non-duplicate extractions.

    Args:
        user: Django User instance.
        user_message: str — the user's message text.
        assistant_response: str — optional assistant response (for context).

    Returns:
        List of LearningExtraction instances created.
    """
    if not user_message or len(user_message) < 10:
        return []

    extractions = []
    msg_lower = user_message.lower().strip()

    for category, patterns in EXTRACTION_PATTERNS.items():
        for pattern in patterns:
            try:
                matches = re.findall(pattern, msg_lower, re.IGNORECASE)
                for match in matches:
                    text = match.strip() if isinstance(match, str) else match
                    if not text or len(text) < 3 or len(text) > 200:
                        continue

                    # Clean up the text
                    text = _clean_extracted_text(text)
                    if not text:
                        continue

                    # Check for duplicates
                    if _is_duplicate(user, category, text):
                        continue

                    extraction = LearningExtraction.objects.create(
                        user=user,
                        category=category,
                        extracted_text=text,
                        source_message=user_message[:500],
                        confidence=0.7,
                    )
                    extractions.append(extraction)

                    # Update profile
                    _add_to_profile(user, category, text)

            except Exception as e:
                logger.debug(f"LearningExtractor: pattern error for {category}: {e}")

    # Update extraction count
    if extractions:
        profile = _get_or_create_profile(user)
        profile.total_extractions += len(extractions)
        profile.last_extraction_at = timezone.now()
        profile.save(update_fields=["total_extractions", "last_extraction_at", "updated_at"])

    return extractions


def get_learned_profile(user):
    """Get or create the user's learned profile."""
    return _get_or_create_profile(user)


def get_profile_system_prompt(user):
    """
    Get the learned profile formatted for system prompt injection.

    Returns empty string if nothing learned yet.
    """
    try:
        profile = UserLearnedProfile.objects.filter(user=user).first()
        if profile:
            return profile.to_system_prompt_block()
    except Exception:
        pass
    return ""


def remove_learned_item(user, category, text):
    """
    Remove a specific learned item from the profile.

    Called when user edits their profile to remove something.
    Full transparency — user controls what's stored.

    Returns:
        True if item was removed, False if not found.
    """
    field = CATEGORY_FIELD_MAP.get(category)
    if not field:
        return False

    try:
        profile = UserLearnedProfile.objects.filter(user=user).first()
        if not profile:
            return False

        items = getattr(profile, field, [])
        if text in items:
            items.remove(text)
            setattr(profile, field, items)
            profile.save(update_fields=[field, "updated_at"])
            return True
    except Exception as e:
        logger.debug(f"LearningExtractor: remove failed: {e}")

    return False


def _get_or_create_profile(user):
    """Get or create UserLearnedProfile."""
    profile, _ = UserLearnedProfile.objects.get_or_create(user=user)
    return profile


def _clean_extracted_text(text):
    """Clean and normalize extracted text."""
    text = text.strip().strip(".,;:!?")
    # Remove very common filler phrases
    filler = ["i think", "i guess", "you know", "basically", "honestly"]
    for f in filler:
        if text.lower().startswith(f):
            text = text[len(f):].strip()
    if len(text) < 3:
        return ""
    return text[:200]


def _is_duplicate(user, category, text):
    """Check if this extraction already exists in the profile."""
    field = CATEGORY_FIELD_MAP.get(category)
    if not field:
        return False

    try:
        profile = UserLearnedProfile.objects.filter(user=user).first()
        if not profile:
            return False

        existing = getattr(profile, field, [])
        text_lower = text.lower()
        for item in existing:
            if text_lower == item.lower() or text_lower in item.lower():
                return True
    except Exception:
        pass

    return False


def _add_to_profile(user, category, text):
    """Add an extracted item to the user's profile."""
    field = CATEGORY_FIELD_MAP.get(category)
    if not field:
        return

    try:
        profile = _get_or_create_profile(user)
        items = getattr(profile, field, []) or []

        if len(items) >= MAX_ITEMS_PER_CATEGORY:
            items = items[1:]  # Remove oldest

        items.append(text)
        setattr(profile, field, items)
        profile.save(update_fields=[field, "updated_at"])
    except Exception as e:
        logger.debug(f"LearningExtractor: profile update failed: {e}")
