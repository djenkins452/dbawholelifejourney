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

# Patterns that indicate the user is reporting they completed an activity.
# Two tiers of confidence:
# - HIGH: Temporal markers ("already", "earlier") or explicit past tense with
#   specific activity → high confidence, auto-complete
# - MEDIUM: "just finished X", "I did my X" — completion verb + activity noun
#   → medium confidence, auto-complete with activity match
#
# Distinct from confirmation_detector.py which handles "yes"/"done" responses
# to quick reply buttons.
AFFIRMED_COMPLETION_PATTERNS = [
    # ── Tier 1: "already" + completion verb (original high-confidence) ──
    r'\balready\s+(did|done|took|finished|completed|logged|handled)\b',
    r'\bi\s+already\s+(did|took|finished|completed|logged|handled|done)\b',
    r'\balready\s+(worked\s+out|exercised|journaled|prayed|read|ate|meditated)\b',
    r'\balready\s+logged\s+(it|that|my)\b',
    r'\balready\s+(got|gotten)\s+(it|that)\s+done\b',
    r'\balready\s+took\s+(it|them|my\s+med|my\s+medicine|my\s+medication)\b',

    # ── Tier 1: Past completion with temporal context ──
    r'\bi\s+(did|took|completed|finished|logged|handled)\s+(it|that|those)\s+(earlier|before|already)\b',
    r'\bi\s+took\s+care\s+of\s+(it|that)\b',
    r'\bi\s+handled\s+(it|that)\s+(earlier|before|already)\b',
    r'\bi\s+got\s+(it|that)\s+done\s+(earlier|before|already)\b',
    r'\bi\s+(did|took|completed|finished)\s+(it|that)\s+(this\s+morning|this\s+afternoon|this\s+evening|last\s+night|before\s+\w+)\b',

    # ── Tier 1: "did it before I saw" / timing-related ──
    r'\bbefore\s+i\s+saw\s+(this|the|your)\b',
    r'\btiming\s+issue\b',
    r'\bdid\s+(it|that)\s+before\b',

    # ── Tier 1: Domain-specific past-tense with temporal ──
    r'\bi\s+(worked\s+out|exercised|journaled|prayed|took\s+my\s+med)\s+(earlier|already|this\s+morning|before)\b',
    r'\bgot\s+my\s+(workout|journal|prayer|meds?|medicine|medication|reading)\s+(done|in)\b',

    # ── Tier 1: "took my [medicine/meds] [temporal]" ──
    r'\btook\s+my\s+(med|meds|medicine|medication|pill|pills)\s+\w*\s*(earlier|before|this\s+morning|this\s+afternoon|last\s+night|already)\b',

    # ── Tier 2: "just finished/did/completed" + activity (no temporal needed) ──
    # "I just finished my journal" / "just did my workout"
    r'\bjust\s+(finished|did|completed|done|took|logged)\s+(my\s+)?\w+',

    # ── Tier 2: "I finished/did/completed my X" (past tense + possessive) ──
    # "I finished my journal" / "I did my workout" / "I completed my prayer"
    r'\bi\s+(finished|completed)\s+my\s+\w+',
    r'\bi\s+did\s+my\s+(journal|workout|exercise|prayer|reading|bible|devotion|meditation|walk|run)\b',

    # ── Tier 2: "X is done" / "X is complete" ──
    # "journal is done" / "workout is done" / "prayer is complete"
    r'\b(journal|workout|exercise|prayer|reading|bible|devotion|medicine|meds?|meditation)\s+is\s+(done|complete|finished)\b',
    r'\bmy\s+(journal|workout|exercise|prayer|reading|bible|devotion|medicine|meds?|meditation)\s+is\s+(done|complete|finished)\b',

    # ── Tier 2: Domain-specific past-tense WITHOUT temporal ──
    # "I journaled" / "I worked out" / "I prayed" / "I took my meds"
    r'\bi\s+(journaled|worked\s+out|exercised|prayed|meditated)\b',
    r'\bi\s+took\s+my\s+(med|meds|medicine|medication|pill|pills)\b',
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

    # Step 5: Auto-complete the corresponding routine/item
    # Uses existing completion pathways (toggle_routine_completion,
    # MedicineLog). No new systems. Failure is non-fatal — user still
    # gets acknowledgment and can manually complete.
    auto_result = _try_auto_complete(user, activity_type, message)

    # Step 6: Build natural response
    response = _build_acknowledgment(activity_type, auto_result)

    logger.info(
        "AFFIRMED_COMPLETION_HANDLED user=%s type=%s confidence=%.2f "
        "auto_complete=%s",
        user.id if hasattr(user, 'id') else user, activity_type, confidence,
        'success' if (auto_result and auto_result.get('completed'))
        else 'already_done' if (auto_result and auto_result.get('already_done'))
        else 'skipped',
    )

    return {
        'handled': True,
        'response': response,
        'activity_type': activity_type,
        'auto_completed': bool(auto_result and auto_result.get('completed')),
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


# ---------------------------------------------------------------------------
# Auto-Complete: Mark items done via existing completion pathways
# ---------------------------------------------------------------------------

# Map activity types to routine task name keywords for matching
_ACTIVITY_TO_ROUTINE_KEYWORDS = {
    'journal': ['journal'],
    'workout': ['workout', 'exercise'],
    'medicine': [],  # Handled separately via MedicineLog
    'faith_prayer': ['prayer'],
    'faith_reading': ['bible', 'reading', 'devotion', 'scripture'],
    'habit': [],
    'task': [],
    'meal': [],
}


def _try_auto_complete(user, activity_type: str, message: str) -> Optional[dict]:
    """Attempt to mark the corresponding routine item complete.

    Uses the existing toggle_routine_completion pathway — no new systems.
    Returns dict with completion details, or None if no matching item found.
    """
    try:
        # Medicine: separate pathway
        if activity_type == 'medicine':
            return _try_auto_complete_medicine(user, message)

        # Routine items: find matching schedule for today
        keywords = _ACTIVITY_TO_ROUTINE_KEYWORDS.get(activity_type, [])
        if not keywords:
            return None

        from apps.core.utils import get_user_today
        from apps.life.models import RoutineLog, RoutineSchedule
        from apps.life.services.routine_helpers import toggle_routine_completion

        today = get_user_today(user)

        # Find active schedules whose task_name matches the activity
        schedules = RoutineSchedule.objects.filter(
            routine__user=user,
            routine__is_active=True,
            is_active=True,
        ).select_related('routine')

        for schedule in schedules:
            task_lower = (schedule.task_name or '').lower()
            if any(kw in task_lower for kw in keywords):
                # Check if already completed today
                existing_log = RoutineLog.objects.filter(
                    user=user,
                    routine_schedule=schedule,
                    date=today,
                    status__in=['completed', 'completed_late'],
                ).first()
                if existing_log:
                    return {
                        'already_done': True,
                        'item_name': schedule.task_name,
                    }

                # Mark complete using existing pathway
                toggle_routine_completion(user, schedule, today)

                logger.info(
                    "AFFIRM_AUTO_COMPLETE user=%s item=%s schedule=%s",
                    user.id, schedule.task_name, schedule.id,
                )
                return {
                    'completed': True,
                    'item_name': schedule.task_name,
                }

        return None

    except Exception as e:
        logger.warning(
            "AFFIRM_AUTO_COMPLETE_FAILED user=%s type=%s error=%s",
            user.id if hasattr(user, 'id') else user,
            activity_type, e, exc_info=True,
        )
        return None


def _try_auto_complete_medicine(user, message: str) -> Optional[dict]:
    """Mark medicine as taken using existing MedicineLog pathway."""
    try:
        from apps.health.models import Medicine, MedicineLog

        today = timezone.now().date()

        # Find active medicines
        active_meds = Medicine.objects.filter(
            user=user,
            medicine_status=Medicine.STATUS_ACTIVE,
        )

        if active_meds.count() == 0:
            return None

        # If only one active medicine, use it directly
        if active_meds.count() == 1:
            med = active_meds.first()
        else:
            # Try to match medicine name from message
            msg_lower = message.lower()
            med = None
            for m in active_meds:
                if m.name.lower() in msg_lower:
                    med = m
                    break

            if not med:
                # Multiple medicines, can't determine which — don't auto-complete
                return None

        # Check if already logged today
        existing = MedicineLog.objects.filter(
            medicine=med,
            date=today,
            status='taken',
        ).first()
        if existing:
            return {
                'already_done': True,
                'item_name': med.name,
            }

        # Log using existing model pathway
        MedicineLog.objects.create(
            medicine=med,
            date=today,
            time=timezone.now().strftime('%H:%M'),
            status='taken',
        )

        logger.info(
            "AFFIRM_AUTO_COMPLETE_MED user=%s med=%s",
            user.id, med.name,
        )
        return {
            'completed': True,
            'item_name': med.name,
        }

    except Exception as e:
        logger.warning(
            "AFFIRM_AUTO_COMPLETE_MED_FAILED user=%s error=%s",
            user.id if hasattr(user, 'id') else user,
            e, exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Response Building
# ---------------------------------------------------------------------------

def _build_acknowledgment(activity_type: str, auto_result: dict = None) -> str:
    """Build a natural acknowledgment response.

    If auto_result is provided and completion succeeded, confirms the
    action was recorded. Otherwise, offers to record it.
    """
    if auto_result and auto_result.get('completed'):
        item = auto_result.get('item_name', activity_type)
        return f"Done — {item} is marked complete."

    if auto_result and auto_result.get('already_done'):
        item = auto_result.get('item_name', activity_type)
        return f"Already logged — {item} was already marked complete."

    # Fallback: couldn't auto-complete, offer to record
    responses = {
        'journal': (
            "Got it — glad you got your journaling in. "
            "If you'd like me to log it, just let me know."
        ),
        'workout': (
            "Nice — sounds like you're staying on top of your training. "
            "If you'd like me to record it, just say the word."
        ),
        'medicine': (
            "Good to hear you're on top of your meds. "
            "If you'd like me to mark them as taken, just let me know."
        ),
        'faith_prayer': (
            "That's great — glad you got your prayer time in. "
            "If you'd like me to log it, I can."
        ),
        'faith_reading': (
            "Good — glad you got your reading done. "
            "If you'd like me to mark it complete, just say so."
        ),
        'habit': (
            "Perfect — sounds like you've got that covered. "
            "If you'd like me to check it off, I can."
        ),
        'task': (
            "Great — sounds like that's taken care of. "
            "If you'd like me to mark it complete, let me know."
        ),
        'meal': (
            "Good — glad you've eaten. "
            "If you'd like me to log it, just let me know."
        ),
    }

    return responses.get(
        activity_type,
        "Got it — I'll take your word for it. "
        "If you'd like me to record it, just let me know."
    )
