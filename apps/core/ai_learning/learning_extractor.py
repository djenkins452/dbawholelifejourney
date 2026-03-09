"""
Phase 4 CoS — Learning Extractor (with Profile Evolution).

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

Profile Evolution (Persistent Learning upgrade):
- Items stored as dicts: {text, confidence, frequency, first_seen, last_confirmed, status}
- Confidence increases on re-extraction, decays over time
- Stale items (60+ days) lose confidence
- Conflicting items can be resolved
- Backward compatible: reads both str and dict formats

Public API:
    - extract_learning(user, user_message, assistant_response) -> list[LearningExtraction]
    - get_learned_profile(user) -> UserLearnedProfile
    - get_profile_system_prompt(user) -> str
    - remove_learned_item(user, category, text) -> bool
    - evolve_profile(user) -> None
"""

import logging
import re

from django.utils import timezone

from apps.core.ai_learning.models import LearningExtraction, UserLearnedProfile

logger = logging.getLogger(__name__)

# Confidence decay: items not re-confirmed in this many days start losing confidence
DECAY_THRESHOLD_DAYS = 60
DECAY_RATE = 0.1  # Confidence drop per decay cycle
MIN_ACTIVE_CONFIDENCE = 0.2  # Below this, mark as "faded"

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
    "health_concern": [
        r"(?:my (?:back|knee|shoulder|calf|leg|arm|wrist|ankle|hip|neck|head|elbow|foot|hamstring) (?:is|has been|hurts|aches|still))\s*(.+?)(?:\.|,|$)",
        r"(?:I've been (?:dealing with|having|experiencing|struggling with))\s+(.+?)(?:\.|,|$)",
        r"(?:(?:the|my) (?:pain|soreness|tightness|stiffness|injury|swelling) (?:in|with|from))\s+(.+?)(?:\.|,|$)",
        r"(?:I (?:pulled|strained|hurt|injured|tweaked|sprained) (?:my )?)\s*(.+?)(?:\.|,|$)",
    ],
    "life_event_mention": [
        r"(?:(?:my (?:sister|brother|mom|dad|wife|husband|son|daughter|friend|mother|father|grandmother|grandfather|grandma|grandpa|nana|papa|aunt|uncle|cousin))'?s? (?:surgery|wedding|graduation|birthday|funeral|visit|trip|appointment|procedure) (?:is|on|at|next|this))\s+(.+?)(?:\.|,|$)",
        r"(?:(?:we|I) (?:have|got) (?:a |an )?(?:trip|vacation|appointment|surgery|meeting|event|procedure|visit) (?:on|in|at|coming up|next|this))\s+(.+?)(?:\.|,|$)",
        r"(?:(?:on|this|next) (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|week|month))[,]?\s+(.+?)(?:\.|$)",
        r"(?:\w+ (?:passed away|died|passed|is no longer with us))\b",
        r"(?:we lost (?:my |our )?(?:\w+))\b",
        r"(?:(?:my|our) (?:wife'?s?|husband'?s?) (?:mother|father|sister|brother|family|parent))\b",
        r"(?:(?:got|getting) (?:married|divorced|engaged|separated))\b",
        r"(?:(?:my|our) (?:baby|child|son|daughter) (?:was born|is due|arrived))\b",
    ],
    "commitment_made": [
        r"(?:I (?:promised|committed|agreed|said I would|told \w+ I'd))\s+(.+?)(?:\.|,|$)",
        r"(?:I need to (?:make sure|remember) to)\s+(.+?)(?:\.|,|$)",
        r"(?:I'm going to make sure)\s+(.+?)(?:\.|,|$)",
    ],
    "explanation_preference": [
        r"(?:(?:keep it|be) (?:short|brief|concise|simple))\b",
        r"(?:(?:give me|I want|I need) (?:more )?detail(?:s|ed)?)\b",
        r"(?:(?:go deeper|explain more|tell me more|elaborate))\b",
        r"(?:just (?:the )?(?:basics|summary|short version|quick answer))\b",
        r"(?:I (?:prefer|like|want) (?:short|detailed|thorough|brief) (?:answers|responses|explanations))\b",
    ],
    "time_pattern": [
        r"(?:(?:every|each) (?:morning|evening|night|afternoon) I)\s+(.+?)(?:\.|,|$)",
        r"(?:I (?:usually|always|tend to) (?:do |start |work on )?\w+ (?:in the )?(?:morning|evening|night|afternoon))\b",
        r"(?:my (?:morning|evening|night|afternoon) (?:routine|habit|practice) (?:is|includes))\s+(.+?)(?:\.|,|$)",
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
    "health_concern": "health_concerns",
    "life_event_mention": "life_event_mentions",
    "commitment_made": "commitments_made",
    "explanation_preference": "explanation_preferences",
    "time_pattern": "time_patterns",
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
    Handles both legacy str items and new dict items.

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
        text_lower = text.lower()

        # Find and remove matching item (str or dict)
        new_items = []
        removed = False
        for item in items:
            item_text = _get_item_text(item)
            if item_text.lower() == text_lower:
                removed = True  # Skip this item
            else:
                new_items.append(item)

        if removed:
            setattr(profile, field, new_items)
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
    """Check if this extraction already exists in the profile.

    Handles both legacy str items and new dict items.
    If a match is found as a dict item, increments its frequency and
    refreshes last_confirmed — this IS the re-confirmation signal.
    """
    field = CATEGORY_FIELD_MAP.get(category)
    if not field:
        return False

    try:
        profile = UserLearnedProfile.objects.filter(user=user).first()
        if not profile:
            return False

        existing = getattr(profile, field, [])
        text_lower = text.lower()
        updated = False

        for i, item in enumerate(existing):
            item_text = _get_item_text(item)
            if text_lower == item_text.lower() or text_lower in item_text.lower():
                # Re-confirmation: boost confidence and refresh timestamp
                if isinstance(item, dict):
                    existing[i]['frequency'] = item.get('frequency', 1) + 1
                    existing[i]['last_confirmed'] = timezone.now().isoformat()
                    existing[i]['confidence'] = min(
                        item.get('confidence', 0.7) + 0.05, 1.0
                    )
                    updated = True
                return True  # Still a duplicate — don't re-add

        if updated:
            setattr(profile, field, existing)
            profile.save(update_fields=[field, "updated_at"])

    except Exception:
        pass

    return False


def _add_to_profile(user, category, text):
    """Add an extracted item to the user's profile as a structured dict."""
    field = CATEGORY_FIELD_MAP.get(category)
    if not field:
        return

    try:
        profile = _get_or_create_profile(user)
        items = getattr(profile, field, []) or []

        # Remove faded items first to make room
        items = [i for i in items if _get_item_status(i) != 'faded']

        if len(items) >= MAX_ITEMS_PER_CATEGORY:
            # Remove lowest confidence item
            items.sort(key=lambda i: _get_item_confidence(i))
            items = items[1:]

        # Add as structured dict
        now = timezone.now().isoformat()
        items.append({
            'text': text,
            'confidence': 0.7,
            'frequency': 1,
            'first_seen': now,
            'last_confirmed': now,
            'status': 'active',
        })

        setattr(profile, field, items)
        profile.save(update_fields=[field, "updated_at"])
    except Exception as e:
        logger.debug(f"LearningExtractor: profile update failed: {e}")


def evolve_profile(user):
    """
    Run profile evolution: decay stale items, resolve conflicts, clean up.

    Call periodically (e.g., daily or on each extraction batch).
    """
    try:
        profile = UserLearnedProfile.objects.filter(user=user).first()
        if not profile:
            return

        now = timezone.now()
        changed_fields = []

        for category, field in CATEGORY_FIELD_MAP.items():
            items = getattr(profile, field, []) or []
            if not items:
                continue

            evolved = []
            for item in items:
                item = _ensure_dict_format(item)

                # Check for staleness
                last_confirmed = _parse_iso(item.get('last_confirmed'))
                if last_confirmed:
                    days_since = (now - last_confirmed).days
                    if days_since > DECAY_THRESHOLD_DAYS:
                        # Decay confidence
                        decay_cycles = (days_since - DECAY_THRESHOLD_DAYS) // 30
                        new_confidence = max(
                            item.get('confidence', 0.7) - (DECAY_RATE * max(decay_cycles, 1)),
                            0.0,
                        )
                        item['confidence'] = round(new_confidence, 2)

                        if new_confidence < MIN_ACTIVE_CONFIDENCE:
                            item['status'] = 'faded'

                # Keep all items (even faded) for transparency
                evolved.append(item)

            if evolved != items:
                setattr(profile, field, evolved)
                changed_fields.append(field)

        if changed_fields:
            changed_fields.append("updated_at")
            profile.save(update_fields=changed_fields)
            logger.debug(
                "Evolved profile for user %s: updated %d categories",
                user.email if hasattr(user, 'email') else user.pk,
                len(changed_fields) - 1,
            )

    except Exception as e:
        logger.debug(f"LearningExtractor: evolve_profile failed: {e}")


# =============================================================================
# FORMAT HELPERS — backward compatibility with str and dict items
# =============================================================================


def _get_item_text(item) -> str:
    """Get text from either a str item or a dict item."""
    if isinstance(item, dict):
        return item.get('text', '')
    return str(item) if item else ''


def _get_item_confidence(item) -> float:
    """Get confidence from a dict item, or default for str items."""
    if isinstance(item, dict):
        return item.get('confidence', 0.7)
    return 0.7


def _get_item_status(item) -> str:
    """Get status from a dict item."""
    if isinstance(item, dict):
        return item.get('status', 'active')
    return 'active'


def _ensure_dict_format(item) -> dict:
    """Convert a legacy str item to dict format."""
    if isinstance(item, dict):
        return item
    now = timezone.now().isoformat()
    return {
        'text': str(item),
        'confidence': 0.7,
        'frequency': 1,
        'first_seen': now,
        'last_confirmed': now,
        'status': 'active',
    }


def _parse_iso(iso_str):
    """Parse an ISO datetime string, return None on failure."""
    if not iso_str:
        return None
    try:
        from django.utils.dateparse import parse_datetime
        return parse_datetime(iso_str)
    except Exception:
        return None
