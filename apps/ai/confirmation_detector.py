# ==============================================================================
# File: apps/ai/confirmation_detector.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detect natural language confirmations for proactive check-ins
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-05
# ==============================================================================
"""
Confirmation Detector

Detects natural language confirmations and negations in user responses
to proactive check-in messages.

Examples:
    - "yes" / "yeah" / "yep" / "sure" → affirmative
    - "no" / "nope" / "not yet" → negative
    - "done" / "took it" / "finished" → affirmative (context-specific)
    - "skip" / "later" → negative/defer
"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Affirmative responses
AFFIRMATIVE_PATTERNS = [
    # Direct affirmatives
    r'\byes\b',
    r'\byeah\b',
    r'\byep\b',
    r'\byup\b',
    r'\bsure\b',
    r'\bok\b',
    r'\bokay\b',
    r'\balright\b',
    r'\baffirmative\b',
    r'\babsolutely\b',
    r'\bdefinitely\b',
    r'\bof course\b',
    r'\byou bet\b',
    r'\bwill do\b',
    r'\bfor sure\b',
    r'\btotally\b',
    r'\byes[!.,]*$',

    # Action confirmations
    r'\bdone\b',
    r'\bdid it\b',
    r'\btook it\b',
    r'\bfinished\b',
    r'\bcompleted\b',
    r'\bi did\b',
    r'\balready did\b',
    r'\bjust did\b',
    r'\bjust took\b',
    r'\bi have\b',
    r'\ball done\b',
    r'\ball set\b',
    r'\bchecked off\b',
    r'\bworked out\b',
    r'\bjournaled\b',
]

# Negative responses
NEGATIVE_PATTERNS = [
    # Direct negatives
    r'\bno\b',
    r'\bnope\b',
    r'\bnot yet\b',
    r'\bnot really\b',
    r'\bnah\b',
    r'\bi haven\'t\b',
    r'\bi didn\'t\b',
    r'\bdidn\'t\b',
    r'\bhaven\'t\b',
    r'\bnot today\b',
    r'\bskip\b',
    r'\bskipping\b',
    r'\bpass\b',
    r'\bforget it\b',
    r'\bmaybe later\b',
    r'\blater\b',
    r'\bnext time\b',
]

# Deferral responses (distinct from negative - means "remind me later")
DEFERRAL_PATTERNS = [
    r'\bremind me later\b',
    r'\blater\b',
    r'\bin a bit\b',
    r'\bin a minute\b',
    r'\bsoon\b',
    r'\bnot right now\b',
    r'\bgive me a moment\b',
    r'\bhold on\b',
]


def detect_confirmation(message: str) -> Tuple[Optional[str], float]:
    """
    Detect if a message is a confirmation, negation, or deferral.

    Args:
        message: The user's message

    Returns:
        Tuple of (response_type, confidence)
        response_type: 'affirmative', 'negative', 'deferral', or None
        confidence: 0.0 to 1.0 indicating how confident the detection is
    """
    message_lower = message.lower().strip()

    # Very short messages are more likely to be direct responses
    is_short = len(message_lower.split()) <= 5

    # Check for affirmative patterns
    for pattern in AFFIRMATIVE_PATTERNS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            confidence = 0.95 if is_short else 0.7
            return ('affirmative', confidence)

    # Check for negative patterns
    for pattern in NEGATIVE_PATTERNS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            confidence = 0.95 if is_short else 0.7
            return ('negative', confidence)

    # Check for deferral patterns
    for pattern in DEFERRAL_PATTERNS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            confidence = 0.85 if is_short else 0.6
            return ('deferral', confidence)

    # No clear confirmation detected
    return (None, 0.0)


def get_most_recent_proactive_message(user) -> Optional[dict]:
    """
    Get the most recent unanswered proactive message for the user.

    Returns the message data if found, or None if no pending check-in.
    """
    from .models import AssistantConversation, AssistantMessage
    from django.utils import timezone
    from datetime import timedelta

    # Look for recent proactive messages (within last 4 hours)
    cutoff = timezone.now() - timedelta(hours=4)

    conversation = AssistantConversation.objects.filter(
        user=user,
        is_active=True
    ).first()

    if not conversation:
        return None

    # Find most recent proactive message with unused quick replies
    proactive_msg = AssistantMessage.objects.filter(
        conversation=conversation,
        is_proactive=True,
        quick_reply_used='',  # Not yet answered
        created_at__gte=cutoff,
    ).exclude(
        quick_replies=[]
    ).order_by('-created_at').first()

    if not proactive_msg:
        return None

    return {
        'id': proactive_msg.id,
        'content': proactive_msg.content,
        'quick_replies': proactive_msg.quick_replies,
        'metadata': proactive_msg.metadata,
        'message': proactive_msg,
    }


def handle_proactive_confirmation(user, message: str) -> Optional[dict]:
    """
    Handle a natural language response to a proactive check-in.

    If the user's message appears to be a response to a recent proactive
    check-in (e.g., "yes" in response to "Did you take your medicine?"),
    this function executes the appropriate action.

    Args:
        user: The User model instance
        message: The user's message

    Returns:
        dict with 'handled' (bool), 'response' (str), and optionally 'action_result'
        or None if no proactive message to handle
    """
    from .quick_reply_handlers import handle_quick_reply

    # Check if there's a pending proactive message
    pending = get_most_recent_proactive_message(user)
    if not pending:
        return None

    # Detect confirmation type
    response_type, confidence = detect_confirmation(message)

    if not response_type or confidence < 0.6:
        return None  # Not a clear confirmation, let normal processing handle it

    quick_replies = pending['quick_replies']
    if not quick_replies:
        return None

    # Map response type to quick reply action
    if response_type == 'affirmative':
        # Find the "primary" or first affirmative quick reply
        for reply in quick_replies:
            if reply.get('style') == 'primary' or 'yes' in reply.get('id', '').lower():
                result = handle_quick_reply(user, reply['action'], reply.get('params', {}))

                # Mark the quick reply as used
                pending['message'].quick_reply_used = reply['id']
                pending['message'].save(update_fields=['quick_reply_used'])

                return {
                    'handled': True,
                    'response': result.get('message', 'Done!'),
                    'action_result': result,
                }

        # Fallback to first reply if no primary
        if quick_replies:
            reply = quick_replies[0]
            result = handle_quick_reply(user, reply['action'], reply.get('params', {}))
            pending['message'].quick_reply_used = reply['id']
            pending['message'].save(update_fields=['quick_reply_used'])
            return {
                'handled': True,
                'response': result.get('message', 'Done!'),
                'action_result': result,
            }

    elif response_type == 'negative':
        # Find a "skip" or "no" quick reply
        for reply in quick_replies:
            if any(word in reply.get('id', '').lower() for word in ['no', 'skip', 'not']):
                result = handle_quick_reply(user, reply['action'], reply.get('params', {}))
                pending['message'].quick_reply_used = reply['id']
                pending['message'].save(update_fields=['quick_reply_used'])
                return {
                    'handled': True,
                    'response': result.get('message', 'Okay!'),
                    'action_result': result,
                }

        # No skip reply found, acknowledge and mark as handled
        pending['message'].quick_reply_used = 'negative_text'
        pending['message'].save(update_fields=['quick_reply_used'])
        return {
            'handled': True,
            'response': "Okay, no problem.",
            'action_result': {'success': True},
        }

    elif response_type == 'deferral':
        # Find a "remind later" quick reply
        for reply in quick_replies:
            if 'remind' in reply.get('id', '').lower() or 'later' in reply.get('id', '').lower():
                result = handle_quick_reply(user, reply['action'], reply.get('params', {}))
                pending['message'].quick_reply_used = reply['id']
                pending['message'].save(update_fields=['quick_reply_used'])
                return {
                    'handled': True,
                    'response': result.get('message', "I'll remind you later."),
                    'action_result': result,
                }

        # No remind reply, just acknowledge
        pending['message'].quick_reply_used = 'deferral_text'
        pending['message'].save(update_fields=['quick_reply_used'])
        return {
            'handled': True,
            'response': "Okay, I'll check back with you later.",
            'action_result': {'success': True},
        }

    return None
