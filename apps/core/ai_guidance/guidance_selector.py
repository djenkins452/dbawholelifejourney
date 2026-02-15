"""
PGE -- Guidance Selector.

Evaluates all registered guidance rules against the user's current state,
recent insights, and predictions. Returns a list of candidate guidance items.
"""

import logging

from apps.core.ai_guidance.guidance_registry import get_guidance_rules

logger = logging.getLogger(__name__)


def select_guidance(user, state, insights, predictions):
    """
    Run all guidance rules and collect candidate items.

    Args:
        user: Django user instance.
        state: Dict from SAE get_user_state().
        insights: QuerySet of recent Insight objects.
        predictions: QuerySet of recent Prediction objects.

    Returns:
        List of guidance candidate dicts.
    """
    candidates = []

    for rule in get_guidance_rules():
        try:
            items = rule.evaluate(user, state, insights, predictions)
            if items:
                candidates.extend(items)
        except Exception as e:
            logger.error(
                f"Guidance rule '{rule.rule_name}' failed for user {user.id}: {e}",
                exc_info=True,
            )

    return candidates
