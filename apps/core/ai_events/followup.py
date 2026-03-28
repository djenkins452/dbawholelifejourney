# ==============================================================================
# File: apps/core/ai_events/followup.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Follow-up resolver for multi-turn event truth continuity
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Event Follow-Up Resolver.

After an event query (e.g., "What did I miss?") returns a deterministic answer,
the user may ask follow-up questions like "What date was that?" or "Which
medication?" This module:

1. Detects follow-up questions (deterministic pattern matching)
2. Resolves them using stored event context (no re-query, no LLM)
3. Returns deterministic answers

The event context is stored in conversation.metadata['recent_event_context']
following the established ECC pattern. It is NOT persistent — it expires
after a configurable number of turns or time window.

Architecture:
    Terminal event route → store context in metadata
    Next message → check for follow-up → resolve from metadata
    No database re-query. No LLM inference. Pure deterministic.
"""

import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# Maximum age of event context before it expires (minutes)
EVENT_CONTEXT_TTL_MINUTES = 30

# Maximum message turns before context expires
EVENT_CONTEXT_MAX_TURNS = 5

# ============================================================================
# Follow-Up Detection
# ============================================================================

# Pronoun/reference patterns that indicate a follow-up to a previous answer
_FOLLOWUP_PATTERNS = (
    # Date questions
    'what date',
    'which date',
    'when was that',
    'when did that happen',
    'what day was that',
    'which day was that',
    'what date did i miss',
    'what date was it',
    'when did i miss it',
    'was that yesterday',
    'was that today',
    'was it yesterday',
    'was it today',
    'was that last week',
    'how many days ago',
    'how long ago',
    # Identity questions
    'which medication',
    'which medicine',
    'which med',
    'which one',
    'what was it',
    'what was that',
    'which dose',
    'what medication was it',
    'what medicine was it',
    'what was the name',
    # Detail questions
    'what time',
    'at what time',
    'what time was it',
    'what was the time',
    'tell me more',
    'more details',
    'can you repeat that',
    'say that again',
    'what did you say',
)


def is_followup_query(msg_lower):
    """
    Detect if a message is a follow-up to a previous event query.

    Only returns True for narrow, high-confidence patterns that clearly
    reference a previous answer. False negatives are safe (fall through
    to normal pipeline). False positives would cause wrong context use.

    Args:
        msg_lower: str — user message, already lowercased

    Returns:
        bool
    """
    return any(p in msg_lower for p in _FOLLOWUP_PATTERNS)


# ============================================================================
# Context Storage
# ============================================================================

def store_event_context(conversation, route_name, events, response_text):
    """
    Store resolved event data in conversation metadata for follow-up access.

    Follows the ECC pattern: conversation.metadata['key'] = value.

    Args:
        conversation: AssistantConversation instance
        route_name: str — which route produced this (e.g., 'event_missed_query')
        events: list[EventRecord] — the resolved events
        response_text: str — the formatted response that was shown to the user
    """
    from django.utils import timezone as tz

    # Serialize EventRecord objects to plain dicts (JSON-safe)
    serialized_events = []
    for e in events:
        serialized_events.append({
            'domain': e.domain,
            'event_type': e.event_type,
            'timestamp': e.timestamp.isoformat() if e.timestamp else None,
            'label': e.label,
            'status': e.status,
            'detail': e.detail,
            'source_model': e.source_model,
            'source_id': e.source_id,
        })

    context = {
        'route_name': route_name,
        'events': serialized_events,
        'event_count': len(serialized_events),
        'response_text': response_text,
        'created_at': tz.now().isoformat(),
        'turns_since': 0,
    }

    conversation.metadata = conversation.metadata or {}
    conversation.metadata['recent_event_context'] = context
    conversation.save(update_fields=['metadata'])

    logger.info(
        "EVENT_CONTEXT_STORED user=%s route=%s events=%d",
        conversation.user_id, route_name, len(serialized_events),
    )


def get_event_context(conversation):
    """
    Retrieve stored event context if it's still valid (not expired).

    Checks both TTL and turn count. Returns None if expired.

    Args:
        conversation: AssistantConversation instance

    Returns:
        dict or None — the stored event context, or None if expired/missing
    """
    metadata = conversation.metadata or {}
    ctx = metadata.get('recent_event_context')
    if not ctx:
        return None

    # Check TTL
    try:
        from django.utils import timezone as tz
        created = datetime.fromisoformat(ctx['created_at'])
        if tz.is_naive(created):
            created = tz.make_aware(created)
        age_minutes = (tz.now() - created).total_seconds() / 60
        if age_minutes > EVENT_CONTEXT_TTL_MINUTES:
            logger.info(
                "EVENT_CONTEXT_EXPIRED user=%s reason=ttl age=%.1fmin",
                conversation.user_id, age_minutes,
            )
            clear_event_context(conversation)
            return None
    except (KeyError, ValueError, TypeError):
        pass

    # Check turn count
    turns = ctx.get('turns_since', 0)
    if turns >= EVENT_CONTEXT_MAX_TURNS:
        logger.info(
            "EVENT_CONTEXT_EXPIRED user=%s reason=turns turns=%d",
            conversation.user_id, turns,
        )
        clear_event_context(conversation)
        return None

    return ctx


def increment_turn_count(conversation):
    """
    Increment the turn counter on event context.

    Called on every message to track how many turns since the event query.
    """
    metadata = conversation.metadata or {}
    ctx = metadata.get('recent_event_context')
    if ctx:
        ctx['turns_since'] = ctx.get('turns_since', 0) + 1
        conversation.metadata['recent_event_context'] = ctx
        conversation.save(update_fields=['metadata'])


def clear_event_context(conversation):
    """Remove event context from conversation metadata."""
    metadata = conversation.metadata or {}
    if 'recent_event_context' in metadata:
        del metadata['recent_event_context']
        conversation.metadata = metadata
        conversation.save(update_fields=['metadata'])


# ============================================================================
# Follow-Up Resolution
# ============================================================================

def resolve_followup(msg_lower, event_context):
    """
    Resolve a follow-up question using stored event context.

    Returns a deterministic response string, or None if the follow-up
    can't be resolved (falls through to normal pipeline).

    Args:
        msg_lower: str — user message, lowercased
        event_context: dict — from get_event_context()

    Returns:
        str or None — deterministic response, or None for fallthrough
    """
    events = event_context.get('events', [])
    if not events:
        return None

    # For single-event context, resolve directly
    if len(events) == 1:
        return _resolve_single_event(msg_lower, events[0])

    # For multi-event context, try to resolve
    return _resolve_multi_event(msg_lower, events)


def _resolve_single_event(msg_lower, event):
    """Resolve follow-up for a single event."""
    detail = event.get('detail', {})

    # ── Date questions ──
    if _is_date_question(msg_lower):
        event_date = detail.get('scheduled_date') or _extract_date_from_timestamp(event)
        if event_date:
            date_obj = _parse_date(event_date)
            if date_obj:
                return _format_date_answer(msg_lower, date_obj)
        return None

    # ── "Was that yesterday/today?" ──
    if _is_relative_date_question(msg_lower):
        event_date = detail.get('scheduled_date') or _extract_date_from_timestamp(event)
        if event_date:
            date_obj = _parse_date(event_date)
            if date_obj:
                return _answer_relative_date(msg_lower, date_obj)
        return None

    # ── Identity questions ("which medication?") ──
    if _is_identity_question(msg_lower):
        name = detail.get('medicine_name') or detail.get('item_name') or event.get('label', '')
        dose = detail.get('dose', '')
        if name:
            answer = f"It was **{name}**"
            if dose:
                answer += f" ({dose})"
            answer += "."
            return answer
        return None

    # ── Time questions ──
    if _is_time_question(msg_lower):
        time_str = detail.get('scheduled_time')
        if time_str:
            return f"It was scheduled for **{time_str}**."
        return None

    # ── Repeat/detail questions ──
    if _is_repeat_question(msg_lower):
        response_text = None
        # Return the original response — it's already deterministic
        return None  # Let it use the original stored response_text

    return None


def _resolve_multi_event(msg_lower, events):
    """Resolve follow-up for multiple events."""
    # For date questions with multiple events, list all dates
    if _is_date_question(msg_lower):
        dates = []
        for e in events:
            d = e.get('detail', {}).get('scheduled_date') or _extract_date_from_timestamp(e)
            if d:
                date_obj = _parse_date(d)
                if date_obj:
                    dates.append((date_obj, e))

        if dates:
            parts = []
            for date_obj, event in dates:
                name = event.get('detail', {}).get('medicine_name') or event.get('detail', {}).get('item_name') or ''
                date_str = _friendly_date(date_obj)
                if name:
                    parts.append(f"• {name} — {date_str}")
                else:
                    parts.append(f"• {date_str}")
            return "Here are the dates:\n" + "\n".join(parts)

    return None


# ============================================================================
# Helpers
# ============================================================================

def _is_date_question(msg_lower):
    return any(p in msg_lower for p in (
        'what date', 'which date', 'when was that', 'when did that',
        'what day', 'which day', 'when did i miss',
        'how many days ago', 'how long ago',
    ))


def _is_relative_date_question(msg_lower):
    return any(p in msg_lower for p in (
        'was that yesterday', 'was it yesterday',
        'was that today', 'was it today',
        'was that last week', 'was it last week',
    ))


def _is_identity_question(msg_lower):
    return any(p in msg_lower for p in (
        'which medication', 'which medicine', 'which med',
        'which one', 'what was it', 'what was that',
        'which dose', 'what medication', 'what medicine',
        'what was the name',
    ))


def _is_time_question(msg_lower):
    return any(p in msg_lower for p in (
        'what time', 'at what time',
    ))


def _is_repeat_question(msg_lower):
    return any(p in msg_lower for p in (
        'tell me more', 'more details', 'can you repeat',
        'say that again', 'what did you say',
    ))


def _extract_date_from_timestamp(event):
    """Extract date string from event timestamp ISO string."""
    ts = event.get('timestamp')
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            return str(dt.date())
        except (ValueError, TypeError):
            pass
    return None


def _parse_date(date_str):
    """Parse a date string to a date object."""
    if isinstance(date_str, date):
        return date_str
    try:
        return date.fromisoformat(str(date_str))
    except (ValueError, TypeError):
        return None


def _format_date_answer(msg_lower, event_date):
    """Format a date answer based on the question type."""
    today = date.today()
    delta = (today - event_date).days

    if 'how many days ago' in msg_lower or 'how long ago' in msg_lower:
        if delta == 0:
            return "That was **today**."
        elif delta == 1:
            return "That was **yesterday** — 1 day ago."
        else:
            return f"That was **{delta} days ago**, on {_friendly_date(event_date)}."

    return f"That was on **{_friendly_date(event_date)}**."


def _answer_relative_date(msg_lower, event_date):
    """Answer yes/no relative date questions."""
    today = date.today()
    delta = (today - event_date).days

    if 'yesterday' in msg_lower:
        if delta == 1:
            return "Yes, that was yesterday."
        elif delta == 0:
            return "No, that was today."
        else:
            return f"No, that was {delta} days ago — {_friendly_date(event_date)}."

    if 'today' in msg_lower:
        if delta == 0:
            return "Yes, that was today."
        elif delta == 1:
            return "No, that was yesterday."
        else:
            return f"No, that was {delta} days ago — {_friendly_date(event_date)}."

    if 'last week' in msg_lower:
        if 7 <= delta <= 13:
            return f"Yes, that was last week — {_friendly_date(event_date)}."
        else:
            return f"No, that was {delta} days ago — {_friendly_date(event_date)}."

    return None


def _friendly_date(d):
    """Format a date in a human-friendly way."""
    today = date.today()
    delta = (today - d).days

    if delta == 0:
        return "today"
    elif delta == 1:
        return "yesterday"
    elif delta < 7:
        return d.strftime("%A")  # "Monday"
    else:
        return d.strftime("%B %-d")  # "March 20"
