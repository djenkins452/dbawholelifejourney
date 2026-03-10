# ==============================================================================
# File: apps/ai/affirmation_detector.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detect user-affirmed completion of activities in conversation
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-09
# ==============================================================================
"""
Affirmation Detector

Detects when a user states they have already completed an activity that
CoS (Beth) reminded them about. Stores the affirmation in conversation
metadata to suppress further reminders — WITHOUT executing any CRUD actions.

This is distinct from confirmation_detector.py which handles quick reply
responses ("yes"/"done") and executes CRUD actions (marks medicine taken, etc.).
The affirmation detector handles "I already did it" statements where the user
completed the activity outside the app and just wants Beth to stop prompting.

Authority hierarchy: User statement overrides system assumptions.

Examples:
    - "I already completed it before I saw this reminder" → affirm journal
    - "I took care of that earlier" → affirm referenced activity
    - "I already worked out this morning" → affirm workout
    - "Already took my meds" → affirm medicine
"""

import logging
import re
from datetime import timedelta
from typing import Optional, Tuple

from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern Detection
# ---------------------------------------------------------------------------

# These patterns require temporal markers (already/before/earlier/this morning)
# to distinguish from simple confirmations handled by confirmation_detector.py.
# "yes" / "done" → confirmation_detector (executes quick reply action)
# "I already did it" → affirmation_detector (suppresses only, no CRUD)
AFFIRMED_COMPLETION_PATTERNS = [
    # "already" + completion verb
    r'\balready\s+(did|done|took|finished|completed|logged|handled)\b',
    r'\bi\s+already\s+(did|took|finished|completed|logged|handled|done)\b',
    r'\balready\s+(worked\s+out|exercised|journaled|prayed|read|ate|meditated)\b',
    r'\balready\s+logged\s+(it|that|my)\b',
    r'\balready\s+(got|gotten)\s+(it|that)\s+done\b',
    r'\balready\s+took\s+(it|them|my\s+med|my\s+medicine|my\s+medication)\b',

    # Past completion with temporal context
    r'\bi\s+(did|took|completed|finished|logged|handled)\s+(it|that|those)\s+(earlier|before|already)\b',
    r'\bi\s+took\s+care\s+of\s+(it|that)\b',
    r'\bi\s+handled\s+(it|that)\s+(earlier|before|already)\b',
    r'\bi\s+got\s+(it|that)\s+done\s+(earlier|before|already)\b',
    r'\bi\s+(did|took|completed|finished)\s+(it|that)\s+(this\s+morning|this\s+afternoon|this\s+evening|last\s+night|before\s+\w+)\b',

    # "did it before I saw" / timing-related
    r'\bbefore\s+i\s+saw\s+(this|the|your)\b',
    r'\btiming\s+issue\b',
    r'\bdid\s+(it|that)\s+before\b',

    # Domain-specific past-tense
    r'\bi\s+(worked\s+out|exercised|journaled|prayed|took\s+my\s+med)\s+(earlier|already|this\s+morning|before)\b',
    r'\bgot\s+my\s+(workout|journal|prayer|meds?|medicine|medication|reading)\s+(done|in)\b',

    # Flexible: "took my [medicine/meds] [temporal]"
    r'\btook\s+my\s+(med|meds|medicine|medication|pill|pills)\s+\w*\s*(earlier|before|this\s+morning|this\s+afternoon|last\s+night|already)\b',
]

# Keyword → activity type mapping for fallback identification
ACTIVITY_KEYWORDS = {
    'journal': 'journal',
    'journaled': 'journal',
    'journaling': 'journal',
    'diary': 'journal',
    'entry': 'journal',
    'workout': 'workout',
    'exercise': 'workout',
    'exercised': 'workout',
    'worked out': 'workout',
    'gym': 'workout',
    'training': 'workout',
    'lift': 'workout',
    'medicine': 'medicine',
    'medication': 'medicine',
    'meds': 'medicine',
    'med': 'medicine',
    'pill': 'medicine',
    'pills': 'medicine',
    'took my': 'medicine',
    'prayer': 'faith_prayer',
    'prayed': 'faith_prayer',
    'praying': 'faith_prayer',
    'devotion': 'faith_reading',
    'devotional': 'faith_reading',
    'bible': 'faith_reading',
    'reading': 'faith_reading',
    'scripture': 'faith_reading',
    'habit': 'habit',
    'routine': 'habit',
    'task': 'task',
    'chore': 'task',
    'meal': 'meal',
    'ate': 'meal',
    'eaten': 'meal',
    'breakfast': 'meal',
    'lunch': 'meal',
    'dinner': 'meal',
}

# Normalize proactive check_in_type to activity category
CHECK_IN_TYPE_MAP = {
    'medicine': 'medicine',
    'medicine_group': 'medicine',
    'workout': 'workout',
    'journal': 'journal',
    'task_overdue': 'task',
    'nn_skip_streak': 'task',
    'faith_reading': 'faith_reading',
    'faith_prayer': 'faith_prayer',
    'finance_budget': 'finance',
    'finance_goal': 'finance',
    'habit_streak': 'habit',
    'journal_concern': 'journal',
    'journal_gap': 'journal',
    'cdce_correlation': 'correlation',
    'busy_day': 'general',
    'pattern': 'general',
    'streak': 'general',
}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_affirmed_completion(message: str) -> Tuple[bool, float]:
    """
    Detect if a message claims prior completion of an activity.

    Returns:
        (is_affirmation, confidence) — e.g. (True, 0.85)

    Distinct from confirmation_detector.detect_confirmation() which handles
    short "yes"/"no" responses to quick reply buttons.
    """
    if not message:
        return (False, 0.0)

    message_lower = message.lower().strip()
    word_count = len(message_lower.split())

    for pattern in AFFIRMED_COMPLETION_PATTERNS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            # Shorter messages with temporal markers are higher confidence
            if word_count <= 8:
                confidence = 0.95
            elif word_count <= 15:
                confidence = 0.85
            else:
                confidence = 0.75
            return (True, confidence)

    return (False, 0.0)


# ---------------------------------------------------------------------------
# Activity Identification
# ---------------------------------------------------------------------------

def identify_affirmed_activity(
    message: str,
    conversation,
) -> Optional[str]:
    """
    Identify which activity type the user is affirming completion of.

    Strategy:
    1. Look at the most recent proactive message in this conversation
       (within last 4 hours) and extract its check_in_type from metadata.
    2. Fall back to keyword matching in the user's message.

    Returns:
        Normalized activity type string (e.g. 'medicine', 'workout', 'journal')
        or None if unidentifiable.
    """
    # Strategy 1: Recent proactive message context
    activity_from_proactive = _get_activity_from_recent_proactive(conversation)
    if activity_from_proactive:
        return activity_from_proactive

    # Strategy 2: Keyword matching in user message
    return _get_activity_from_keywords(message)


def _get_activity_from_recent_proactive(conversation) -> Optional[str]:
    """Extract activity type from the most recent proactive check-in message."""
    try:
        from .models import AssistantMessage

        cutoff = timezone.now() - timedelta(hours=4)
        proactive_msg = AssistantMessage.objects.filter(
            conversation=conversation,
            is_proactive=True,
            created_at__gte=cutoff,
        ).order_by('-created_at').first()

        if not proactive_msg:
            return None

        metadata = proactive_msg.metadata or {}
        check_in_type = metadata.get('check_in_type', '')
        if check_in_type:
            return CHECK_IN_TYPE_MAP.get(check_in_type, check_in_type)

        return None
    except Exception:
        logger.warning("Failed to get activity from proactive message", exc_info=True)
        return None


def _get_activity_from_keywords(message: str) -> Optional[str]:
    """Extract activity type from keywords in the user's message."""
    if not message:
        return None

    message_lower = message.lower()

    # Check multi-word keywords first (longer matches take priority)
    sorted_keywords = sorted(ACTIVITY_KEYWORDS.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in message_lower:
            return ACTIVITY_KEYWORDS[keyword]

    return None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store_affirmed_completion(conversation, activity_type: str) -> None:
    """
    Store the affirmed completion in conversation.metadata.

    Schema:
        conversation.metadata['affirmed_completions'] = {
            'medicine': '2026-03-09T14:30:00+00:00',
            'workout': '2026-03-09T15:15:00+00:00',
        }

    Uses the established metadata pattern from personal_assistant.py.
    Affirmed completions clear automatically when conversation.clear_messages()
    is called (which resets metadata to {}).
    """
    if not conversation:
        return

    metadata = conversation.metadata or {}
    affirmed = metadata.get('affirmed_completions', {})
    affirmed[activity_type] = timezone.now().isoformat()
    metadata['affirmed_completions'] = affirmed
    conversation.metadata = metadata
    conversation.save(update_fields=['metadata'])

    logger.info(
        "AFFIRMED_COMPLETION user=%s type=%s — "
        "stored in conversation metadata, will suppress further reminders",
        conversation.user_id, activity_type,
    )


def get_affirmed_completions(conversation) -> dict:
    """
    Get the current affirmed completions for this conversation.

    Returns:
        Dict mapping activity_type -> ISO timestamp string.
        Empty dict if none.
    """
    if not conversation:
        return {}

    metadata = conversation.metadata or {}
    return metadata.get('affirmed_completions', {})


def is_activity_affirmed(conversation, check_in_type: str) -> bool:
    """
    Check if a specific check_in_type has been user-affirmed.

    Normalizes the check_in_type using CHECK_IN_TYPE_MAP
    (e.g. 'medicine_group' → 'medicine').
    """
    if not conversation:
        return False

    normalized = CHECK_IN_TYPE_MAP.get(check_in_type, check_in_type)
    affirmed = get_affirmed_completions(conversation)
    return normalized in affirmed


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def handle_affirmed_completion(
    user,
    message: str,
    conversation,
) -> Optional[dict]:
    """
    Main entry point. Detects and processes user-affirmed completions.

    Must run BEFORE confirmation_detector.handle_proactive_confirmation()
    to prevent CRUD actions when user only wants to suppress reminders.

    Returns:
        dict with:
            'handled': True,
            'response': natural acknowledgment,
            'activity_type': 'medicine',
        or None if not an affirmation.
    """
    # Step 1: Detect affirmation pattern
    is_affirmation, confidence = detect_affirmed_completion(message)
    if not is_affirmation or confidence < 0.6:
        return None

    # Step 2: Identify which activity
    activity_type = identify_affirmed_activity(message, conversation)
    if not activity_type:
        # Can't determine which activity — fall through to normal processing.
        # The LLM will handle it conversationally.
        return None

    # Step 3: Store the affirmation (suppresses future check-ins)
    store_affirmed_completion(conversation, activity_type)

    # Step 4: Mark the proactive message as handled (if any)
    _mark_proactive_as_handled(conversation, activity_type)

    # Step 5: Build natural response
    response = _build_acknowledgment(activity_type)

    logger.info(
        "AFFIRMED_COMPLETION_HANDLED user=%s type=%s confidence=%.2f — "
        "no CRUD executed, suppressing further reminders",
        user.id if hasattr(user, 'id') else user, activity_type, confidence,
    )

    return {
        'handled': True,
        'response': response,
        'activity_type': activity_type,
    }


def _mark_proactive_as_handled(conversation, activity_type: str) -> None:
    """Mark the most recent proactive message for this type as handled."""
    try:
        from .models import AssistantMessage

        cutoff = timezone.now() - timedelta(hours=4)
        normalized = CHECK_IN_TYPE_MAP.get(activity_type, activity_type)

        # Find matching proactive message
        proactive_msg = AssistantMessage.objects.filter(
            conversation=conversation,
            is_proactive=True,
            quick_reply_used='',
            created_at__gte=cutoff,
        ).order_by('-created_at').first()

        if proactive_msg:
            msg_type = (proactive_msg.metadata or {}).get('check_in_type', '')
            msg_normalized = CHECK_IN_TYPE_MAP.get(msg_type, msg_type)
            if msg_normalized == normalized or not msg_type:
                proactive_msg.quick_reply_used = 'user_affirmed'
                proactive_msg.save(update_fields=['quick_reply_used'])
    except Exception:
        logger.warning(
            "Failed to mark proactive message as handled", exc_info=True
        )


def _build_acknowledgment(activity_type: str) -> str:
    """Build a natural acknowledgment response."""
    # Activity-specific acknowledgments
    responses = {
        'journal': (
            "Got it \u2014 glad you got your journaling in. "
            "If you'd like me to log it for you, just let me know."
        ),
        'workout': (
            "Nice \u2014 sounds like you're staying on top of your training. "
            "If you'd like me to record it, just say the word."
        ),
        'medicine': (
            "Good to hear you're on top of your meds. "
            "If you'd like me to mark them as taken, just let me know."
        ),
        'faith_prayer': (
            "That's great \u2014 glad you got your prayer time in. "
            "If you'd like me to log it, I can."
        ),
        'faith_reading': (
            "Good \u2014 glad you got your reading done. "
            "If you'd like me to mark it complete, just say so."
        ),
        'habit': (
            "Perfect \u2014 sounds like you've got that covered. "
            "If you'd like me to check it off, I can."
        ),
        'task': (
            "Great \u2014 sounds like that's taken care of. "
            "If you'd like me to mark it complete, let me know."
        ),
        'meal': (
            "Good \u2014 glad you've eaten. "
            "If you'd like me to log it, just let me know."
        ),
    }

    return responses.get(
        activity_type,
        "Got it \u2014 I'll take your word for it. "
        "If you'd like me to record it, just let me know."
    )
