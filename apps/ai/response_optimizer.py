# ==============================================================================
# File: response_optimizer.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adaptive response optimization for CoS. Learns which response
#              characteristics work best for each user based on feedback.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Adaptive Response Optimization Service

Tracks response characteristics that correlate with positive/negative feedback
and adjusts future responses accordingly.

Public API:
  - record_feedback(user, message, was_helpful) -> None
  - get_response_preference(user) -> ResponsePreference
  - get_preference_prompt_block(user) -> str
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Response length buckets (word count thresholds)
LENGTH_BUCKETS = {
    'concise': (0, 80),
    'balanced': (81, 200),
    'detailed': (201, float('inf')),
}

# Traits to detect in responses
TRAIT_DETECTORS = {
    'uses_lists': lambda text: text.count('\n-') >= 2 or text.count('\n•') >= 2,
    'asks_questions': lambda text: text.count('?') >= 1,
    'uses_encouragement': lambda text: any(
        w in text.lower() for w in [
            'great job', 'well done', 'proud', 'amazing', 'keep it up',
            'nice work', 'excellent', 'good for you',
        ]
    ),
    'uses_scripture': lambda text: any(
        w in text.lower() for w in [
            'scripture', 'verse', 'bible', 'psalm', 'proverbs',
            'matthew', 'john', 'romans', 'genesis',
        ]
    ),
    'uses_data': lambda text: any(
        c.isdigit() for c in text[:200]
    ) and any(w in text.lower() for w in ['%', 'average', 'total', 'streak']),
    'gives_action_items': lambda text: any(
        w in text.lower() for w in [
            'try this', 'consider', 'i suggest', 'you could',
            'here\'s what', 'next step', 'action',
        ]
    ),
}


def record_feedback(user, message_content: str, was_helpful: bool) -> None:
    """
    Record feedback on a response and update learned preferences.

    Called when the user rates a message via the feedback endpoint.

    Args:
        user: Django User instance.
        message_content: The assistant's response text.
        was_helpful: Whether the user found it helpful.
    """
    from .models import ResponsePreference

    try:
        pref, _ = ResponsePreference.objects.get_or_create(user=user)

        # Update counters
        if was_helpful:
            pref.helpful_count += 1
        else:
            pref.unhelpful_count += 1

        # Analyze response characteristics
        word_count = len(message_content.split())
        response_length = _classify_length(word_count)

        # Update length preference based on feedback pattern
        pref.preferred_length = _compute_preferred_length(pref, response_length, was_helpful)

        # Update coaching style scores
        _update_style_scores(pref, user, was_helpful)

        # Update trait effectiveness
        _update_trait_scores(pref, message_content, was_helpful)

        pref.save()

        logger.debug(
            "Updated response preferences for user %s: "
            "helpful=%s, length=%s, preferred=%s",
            user.email, was_helpful, response_length, pref.preferred_length,
        )

    except Exception as e:
        logger.warning("Failed to update response preferences: %s", e)


def get_response_preference(user) -> Optional['ResponsePreference']:
    """Get the user's learned response preference, if any."""
    from .models import ResponsePreference
    try:
        return ResponsePreference.objects.filter(user=user).first()
    except Exception:
        return None


def get_preference_prompt_block(user) -> str:
    """
    Build the system prompt injection block for response preferences.

    Returns empty string if not enough data.
    """
    pref = get_response_preference(user)
    if not pref:
        return ""
    return pref.to_system_prompt_block()


def _classify_length(word_count: int) -> str:
    """Classify response length into buckets."""
    for label, (lo, hi) in LENGTH_BUCKETS.items():
        if lo <= word_count <= hi:
            return label
    return 'detailed'


def _compute_preferred_length(pref, current_length: str, was_helpful: bool) -> str:
    """
    Compute the preferred length based on accumulated feedback.

    Uses exponential moving average approach — recent feedback
    matters more but doesn't completely override history.
    """
    # Track length-specific scores in effective_traits
    traits = pref.effective_traits or {}

    for length_key in ['concise', 'balanced', 'detailed']:
        score_key = f'length_{length_key}'
        if score_key not in traits:
            traits[score_key] = 0.0

    # Update the score for the current length
    score_key = f'length_{current_length}'
    current_score = traits.get(score_key, 0.0)

    if was_helpful:
        traits[score_key] = current_score + 0.1
    else:
        traits[score_key] = current_score - 0.1

    pref.effective_traits = traits

    # Determine preferred length from scores
    length_scores = {
        'concise': traits.get('length_concise', 0.0),
        'balanced': traits.get('length_balanced', 0.0),
        'detailed': traits.get('length_detailed', 0.0),
    }

    return max(length_scores, key=length_scores.get)


def _update_style_scores(pref, user, was_helpful: bool):
    """Update coaching style effectiveness scores."""
    try:
        style = user.preferences.ai_coaching_style or 'supportive'
    except Exception:
        style = 'supportive'

    scores = pref.style_scores or {}
    if style not in scores:
        scores[style] = {'helpful': 0, 'unhelpful': 0}

    if was_helpful:
        scores[style]['helpful'] += 1
    else:
        scores[style]['unhelpful'] += 1

    pref.style_scores = scores


def _update_trait_scores(pref, message_content: str, was_helpful: bool):
    """Update trait effectiveness scores based on which traits are present."""
    traits = pref.effective_traits or {}

    for trait_name, detector in TRAIT_DETECTORS.items():
        try:
            if detector(message_content):
                current = traits.get(trait_name, 0.0)
                if was_helpful:
                    traits[trait_name] = min(current + 0.05, 1.0)
                else:
                    traits[trait_name] = max(current - 0.05, -1.0)
        except Exception:
            pass

    pref.effective_traits = traits
