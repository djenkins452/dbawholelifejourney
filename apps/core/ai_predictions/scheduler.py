"""
PRIE — Scheduler.

Daily prediction generation for all active users.
"""

import logging

from django.utils import timezone

from apps.core.ai_predictions.prediction_engine import generate_predictions

logger = logging.getLogger(__name__)


def run_predictions_for_user(user):
    """
    Run all prediction rules for a single user.

    Generates predictions across all modules.
    """
    try:
        predictions = generate_predictions(user, module="all")
        return predictions
    except Exception as e:
        logger.error(
            f"Daily predictions failed for user {user.id}: {e}",
            exc_info=True,
        )
        return []


def run_predictions_all_users():
    """Run predictions for all active users."""
    from apps.users.models import User

    active_users = User.objects.filter(is_active=True)
    total = 0
    for user in active_users:
        predictions = run_predictions_for_user(user)
        total += len(predictions)

    logger.info(f"Daily predictions complete: {total} predictions for {active_users.count()} users")
    return total
