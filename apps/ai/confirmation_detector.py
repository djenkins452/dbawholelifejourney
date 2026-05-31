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

# Same-day defer phrases — user still intends today, just not now.
# Used by the routine-nudge defer guard (trust-correct path: no schedule
# mutation, no action card). Distinct from DEFERRAL_PATTERNS because we
# want broader coverage of "today but later" wording.
SAME_DAY_DEFER_PATTERNS = [
    r'\blater\b',
    r'\bmaybe later\b',
    r'\bnot now\b',
    r'\bnot right now\b',
    r'\bnot yet\b',
    r'\bin a bit\b',
    r'\bin a minute\b',
    r'\bgive me a moment\b',
    r'\bgive me (?:a|an) (?:few |couple )?(?:minute|hour|sec)s?\b',
    r'\bhold on\b',
    r'\bsoon\b',
    r'\bafter (?:chores|dinner|lunch|breakfast|work|that|this|them)\b',
    r"\bwhen i(?:'m| am)?\s*(?:finish|done|get done)\w*\b",
    r"\bonce i(?:'m| am)?\s*(?:finish|done)\w*\b",
    r'\bthis (?:afternoon|evening|morning)\b',
    r'\btonight\b',
    r'\blater today\b',
    r'\bi can (?:still )?(?:do|get to) (?:it|that|this)\b',
    r'\bi(?:\'ll| will) (?:shower|do|finish|get to|handle) (?:it|that|this)?\b',
]

# Phrases that REJECT the same-day-defer interpretation — these indicate
# the user actually wants a true reschedule / day shift / skip / cancel.
# Anything matching these falls through to the existing intent pipeline.
_EXPLICIT_RESCHEDULE_SIGNALS = [
    r'\b\d{1,2}:\d{2}\b',                       # 7:30, 19:00
    r'\b\d{1,2}\s?(?:am|pm|a\.m\.|p\.m\.)\b',   # 7am, 7 pm, 7 PM
    r'\b(?:at|by)\s+\d{1,2}\b',                 # at 7, by 5
    r'\bnoon\b',
    r'\bmidnight\b',
    r'\btomorrow\b',
    r'\bnext\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\bskip\b',
    r'\bcancel\b',
    r'\bdelete\b',
    r'\breschedule\b',
    r'\bmove (?:it|that|this|to)\b',
    r'\bpush (?:it|that|this|to)\b',
    r'\bwon\'?t (?:get to|do|make|finish)\b',   # "I won't get to this today" → day shift
    r'\bnot today\b',
]


def is_timeless_same_day_defer(message: str) -> bool:
    """Return True when the message reads as "still today, just not now."

    Must match at least one SAME_DAY_DEFER_PATTERNS phrase AND contain no
    explicit reschedule/skip/day-shift signal. Used by the routine-nudge
    defer guard.
    """
    if not message:
        return False
    text = message.lower().strip()
    if not any(re.search(p, text, re.IGNORECASE) for p in SAME_DAY_DEFER_PATTERNS):
        return False
    if any(re.search(p, text, re.IGNORECASE) for p in _EXPLICIT_RESCHEDULE_SIGNALS):
        return False
    return True


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


def _get_recent_proactive_nudge(user, max_age_hours: int = 4):
    """Return the user's most recent proactive nudge (with or without
    quick replies) within the last `max_age_hours`, or None.

    Distinct from `get_most_recent_proactive_message` which filters out
    messages with no quick replies — the routine-nudge defer guard needs
    to fire for plain-text proactive nudges too (midday alignment,
    afternoon momentum, evening wrap all render without quick replies).
    """
    from .models import AssistantConversation, AssistantMessage
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(hours=max_age_hours)
    conversation = AssistantConversation.objects.filter(
        user=user, is_active=True,
    ).first()
    if not conversation:
        return None
    return AssistantMessage.objects.filter(
        conversation=conversation,
        is_proactive=True,
        created_at__gte=cutoff,
    ).order_by('-created_at').first()


# Pattern used by _render_midday: "<Label> (<time>) has slipped."
_SLIPPED_PATTERN = re.compile(
    r'^\s*(.+?)(?:\s*\([^)]+\))?\s+has slipped\.',
    re.MULTILINE | re.IGNORECASE,
)
# Bulleted slipping list: "Slipping:\n• X\n• Y"
_SLIPPING_BULLET_PATTERN = re.compile(
    r'(?im)^\s*[•*-]\s*(.+?)\s*$',
)


def _extract_routine_label_from_nudge(content: str, user_message: str = "") -> Optional[str]:
    """Best-effort extraction of the routine item label from a proactive
    nudge so the same-day defer ack can say "leave Shower on today's list."

    Strategy:
      1. If `user_message` mentions any candidate item by keyword, prefer it.
      2. Else extract the first "<X> has slipped." label.
      3. Else extract the first bullet under "Slipping:".
      4. Else return None (caller falls back to generic wording).
    """
    if not content:
        return None

    candidates: list[str] = []
    m = _SLIPPED_PATTERN.search(content)
    if m:
        candidates.append(m.group(1).strip())

    if 'Slipping:' in content or '\nSlipping:' in content:
        # Collect bullets only from the "Slipping:" section.
        chunk = content.split('Slipping:', 1)[1]
        for bullet_match in _SLIPPING_BULLET_PATTERN.finditer(chunk):
            label = bullet_match.group(1).strip()
            # Stop at the next section header (next blank line + non-bullet).
            if label and not label.startswith(('+', '…')):
                candidates.append(label)

    if not candidates:
        return None

    # Prefer the candidate the user named in their reply.
    if user_message:
        msg_lower = user_message.lower()
        for c in candidates:
            tokens = [t for t in re.split(r'\W+', c.lower()) if len(t) > 2]
            if any(t in msg_lower for t in tokens):
                return c

    return candidates[0]


def _get_proactive_pending_context(user) -> Optional[dict]:
    """
    Look up the active proactive PendingAction for this user.

    Returns entity context dict (task_id, intent_type, etc.) or None.
    Uses cache first (fast), falls back to DB (durable).
    """
    try:
        from django.core.cache import cache
        from django.utils import timezone

        # Fast path: cache lookup
        cache_key = f"pending_proactive_{user.id}"
        cached = cache.get(cache_key)
        if cached:
            return {
                'pending_action_id': cached.get('action_id'),
                'intent_type': cached.get('intent_type', ''),
                **cached.get('parameters', {}),
            }

        # Slow path: DB fallback (cache eviction recovery)
        from apps.core.ai_governance.models import PendingAction
        pa = PendingAction.objects.filter(
            user=user,
            action_type='proactive_checkin',
            status=PendingAction.STATUS_PENDING,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at').first()

        if pa:
            return {
                'pending_action_id': str(pa.id),
                'intent_type': pa.intent_type,
                **pa.parameters,
            }
    except Exception as e:
        logger.warning("Failed to look up proactive PendingAction: %s", e)

    return None


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

    # ── SAME-DAY DEFER GUARD (trust-correct path) ────────────────────
    # If Beth recently sent a proactive routine nudge AND the user's
    # reply reads as "still today, just later" with no explicit time or
    # day-shift signal, acknowledge conversationally — no schedule
    # mutation, no action card, no LLM call. The task stays on today's
    # list and Beth re-surfaces it later if still incomplete.
    #
    # Scoped narrowly: requires a recent is_proactive=True message so
    # generic chat phrases like "I'll do that later" cannot globally
    # suppress valid intent routing elsewhere in WLJ.
    if is_timeless_same_day_defer(message):
        recent_nudge = _get_recent_proactive_nudge(user)
        if recent_nudge is not None:
            label = _extract_routine_label_from_nudge(
                recent_nudge.content or "", user_message=message,
            )
            if label:
                ack = (
                    f"Understood. I'll leave {label} on today's list "
                    f"and check back later."
                )
            else:
                ack = (
                    "Understood. I'll leave it on today's list and "
                    "check back later."
                )
            # Mark the nudge as handled so we don't double-process it.
            if not recent_nudge.quick_reply_used:
                recent_nudge.quick_reply_used = 'same_day_defer_text'
                recent_nudge.save(update_fields=['quick_reply_used'])
            logger.info(
                "SAME_DAY_DEFER_ACK user=%s label=%s nudge_id=%s",
                getattr(user, 'id', '?'), label or '<generic>',
                recent_nudge.id,
            )
            return {
                'handled': True,
                'response': ack,
                'action_result': {
                    'success': True,
                    'action_type': 'same_day_defer_acknowledge',
                },
            }

    # Check if there's a pending proactive message
    pending = get_most_recent_proactive_message(user)
    if not pending:
        return None

    # Detect confirmation type
    response_type, confidence = detect_confirmation(message)

    if not response_type or confidence < 0.6:
        # Not a clear confirmation — but if there's a PendingAction with entity
        # context, pass it through so the intent pipeline can use the entity_id
        # instead of falling back to fragile title text-matching.
        pending_context = _get_proactive_pending_context(user)
        if pending_context:
            return {
                'handled': False,
                'pending_context': pending_context,
            }
        return None

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
