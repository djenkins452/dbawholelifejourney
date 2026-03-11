"""
Decision Memory — Tracks repeated user choices for structured confirmations.

Learns that a user tends to pick the same option (e.g., "entire series")
for similar action contexts. Used to SUGGEST (not auto-execute) preferred
options by reordering them in the A/B/C list.

Thresholds:
- sample_size >= 5: minimum observations before suggesting
- confidence >= 0.70: minimum agreement rate
- Decay: 0.02 per day since last interaction (prevents stale preferences)

Safety: NEVER auto-executes based on learned preferences.
"""

import hashlib
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_decision_suggestion(
    user,
    intent_type: str,
    context_key: str,
) -> Optional[Dict]:
    """
    Check if the user has a strong preference for this action context.

    Args:
        user: Django user instance.
        intent_type: The intent being confirmed.
        context_key: Normalized context identifier (e.g., 'recurring', 'default').

    Returns:
        {'suggested_action': str, 'confidence': float, 'sample_size': int}
        or None if no reliable preference exists.
    """
    try:
        from apps.core.ai_governance.models import UserDecisionPreference
        pref = UserDecisionPreference.objects.get(
            user=user,
            intent_type=intent_type,
            context_key=context_key,
        )
        if pref.is_reliable():
            return {
                'suggested_action': pref.preferred_action,
                'confidence': pref.get_effective_confidence(),
                'sample_size': pref.sample_size,
            }
    except Exception:
        pass  # Model not found or DB error — no suggestion
    return None


def record_decision(
    user,
    intent_type: str,
    context_key: str,
    action: str,
):
    """
    Record a user's confirmation decision for learning.

    Creates or updates the UserDecisionPreference for this context.
    Errors are logged but never block the main flow.

    Args:
        user: Django user instance.
        intent_type: The intent that was confirmed.
        context_key: Normalized context identifier.
        action: The action the user chose (confirm, cancel, edit, or custom).
    """
    try:
        from apps.core.ai_governance.models import UserDecisionPreference
        pref, _ = UserDecisionPreference.objects.get_or_create(
            user=user,
            intent_type=intent_type,
            context_key=context_key,
        )
        pref.record_decision(action)
        logger.info(
            "[DECISION_MEMORY] Recorded: user=%s intent=%s context=%s "
            "action=%s → preferred=%s confidence=%.2f n=%d",
            user.id, intent_type, context_key,
            action, pref.preferred_action, pref.confidence, pref.sample_size,
        )
    except Exception as e:
        logger.error(
            "[DECISION_MEMORY] Failed to record decision: %s", e,
            exc_info=True,
        )


def compute_context_key(intent_type: str, parameters: dict) -> str:
    """
    Compute a stable context key for decision memory.

    Groups similar actions so preferences transfer across identical contexts.
    For example, all recurring task mutations share context_key='recurring'.

    Args:
        intent_type: The intent type.
        parameters: The action parameters.

    Returns:
        A short, human-readable context key.
    """
    # Recurring task mutations
    if intent_type in ('mutate_task', 'mutate_calendar_event'):
        if parameters.get('action') == 'delete':
            if parameters.get('delete_series') is not None:
                return 'delete_recurring'
            return 'delete'
        return 'update'

    # Health logs (all similar)
    if intent_type.startswith('log_'):
        return 'log'

    # Creates
    if intent_type.startswith('create_'):
        return 'create'

    # Default
    return 'default'


def apply_suggestion_to_options(
    options: list,
    suggestion: Optional[Dict],
) -> list:
    """
    Reorder options so the suggested option appears first.

    Marks the suggested option with is_suggested=True.
    Re-assigns letter keys (A, B, C, ...) after reordering.

    Args:
        options: List of option dicts.
        suggestion: Result from get_decision_suggestion, or None.

    Returns:
        Reordered options list (or original if no suggestion).
    """
    if not suggestion or not options:
        return options

    suggested_action = suggestion.get('suggested_action')
    if not suggested_action:
        return options

    # Find the suggested option
    suggested_idx = None
    for i, opt in enumerate(options):
        if opt.get('action') == suggested_action:
            suggested_idx = i
            break

    if suggested_idx is None or suggested_idx == 0:
        # Already first or not found
        if suggested_idx == 0:
            options[0]['is_suggested'] = True
        return options

    # Move suggested option to front
    reordered = [options[suggested_idx]] + [
        o for i, o in enumerate(options) if i != suggested_idx
    ]

    # Re-assign letter keys and mark suggested
    for i, opt in enumerate(reordered):
        opt['key'] = chr(ord('A') + i)
        opt['is_suggested'] = (i == 0)

    return reordered
