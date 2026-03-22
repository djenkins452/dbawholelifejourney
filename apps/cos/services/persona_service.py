"""
Persona Message Rendering Service

Config-driven message rendering that combines:
  - User's CoachingStyle (DB-driven persona)
  - Day status (low/partial/strong from completion rate)
  - Message type (next_action, day_summary, nudge, etc.)

Architecture rules:
  - ONLY formats text — never changes action selection, priority, or data
  - Falls back gracefully: user style → default style → hardcoded fallback
  - All templates use Python str.format() with named placeholders
"""

import logging

logger = logging.getLogger(__name__)

# ── Message types (strict contract) ──
MESSAGE_TYPES = {
    'next_action',
    'day_summary',
    'nudge',
    'empty_state',
    'progress_update',
}

# ── Day status levels ──
DAY_STATUSES = {'low', 'partial', 'strong'}

# ── Hardcoded fallback templates (always available) ──
_FALLBACK_TEMPLATES = {
    'next_action': {
        'low': "Start with {action}. Take {duration} minutes right now.",
        'partial': "Next up: {action} ({duration} min).",
        'strong': "Keep going — next is {action}.",
    },
    'day_summary': {
        'low': "You're at {completion_rate}% today. Pick one thing and start there.",
        'partial': "You're making progress — {completed}/{total} done. Keep going.",
        'strong': "Strong day — {completed}/{total} done.",
    },
    'nudge': {
        'low': "{action} needs attention.",
        'partial': "Don't forget: {action}.",
        'strong': "One more to close out: {action}.",
    },
    'empty_state': {
        'low': "Nothing completed yet. What's the first move?",
        'partial': "Nothing completed yet. What's the first move?",
        'strong': "Nothing completed yet. What's the first move?",
    },
    'progress_update': {
        'low': "{completed} of {total} done.",
        'partial': "{completed} of {total} done — good progress.",
        'strong': "{completed} of {total} done — great work.",
    },
}


def get_user_persona_templates(user):
    """
    Get the message templates for a user's active coaching style.

    Returns the templates dict from CoachingStyle.message_templates,
    or empty dict if none configured.
    """
    try:
        from apps.ai.models import CoachingStyle
        style_key = getattr(user.preferences, 'ai_coaching_style', 'supportive')
        style = CoachingStyle.get_by_key(style_key)
        if style and style.message_templates:
            return style.message_templates
    except Exception:
        logger.debug("Failed to load persona templates", exc_info=True)
    return {}


def render_message(user, message_type, context, day_status='partial'):
    """
    Render a persona-aware message.

    Args:
        user: Django User instance
        message_type: str — one of MESSAGE_TYPES
        context: dict — template variables (action, duration, completed, total, etc.)
        day_status: str — 'low', 'partial', or 'strong'

    Returns:
        str — rendered message, or empty string if message_type is invalid

    Fallback chain:
        1. User's CoachingStyle.message_templates[message_type][day_status]
        2. _FALLBACK_TEMPLATES[message_type][day_status]
        3. _FALLBACK_TEMPLATES[message_type]['partial']
        4. Empty string (should never happen)
    """
    if message_type not in MESSAGE_TYPES:
        logger.warning("Unknown message_type: %s", message_type)
        return ''

    # Normalize day_status
    if day_status not in DAY_STATUSES:
        day_status = 'partial'

    # Try user's persona templates first
    user_templates = get_user_persona_templates(user)
    template = None

    if user_templates:
        type_templates = user_templates.get(message_type, {})
        template = type_templates.get(day_status)

    # Fallback to hardcoded defaults
    if not template:
        fallback_type = _FALLBACK_TEMPLATES.get(message_type, {})
        template = fallback_type.get(day_status) or fallback_type.get('partial', '')

    if not template:
        return ''

    # Render with safe formatting (missing keys → kept as placeholders)
    try:
        return template.format_map(_SafeFormatDict(context))
    except Exception:
        logger.warning("Template render failed: %s", template, exc_info=True)
        return template


def get_day_status_from_rate(completion_rate):
    """
    Convert completion rate percentage to day status string.

    Args:
        completion_rate: int (0-100)

    Returns:
        str — 'low', 'partial', or 'strong'
    """
    if completion_rate >= 75:
        return 'strong'
    elif completion_rate >= 40:
        return 'partial'
    return 'low'


class _SafeFormatDict(dict):
    """Dict that returns '{key}' for missing keys instead of raising KeyError."""

    def __missing__(self, key):
        return '{' + key + '}'
