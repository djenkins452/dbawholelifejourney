"""
PIE Scheduler — Run daily insight checks.
"""

import logging

from apps.core.ai_insights.insight_engine import run_insights
from apps.core.time.system_clock import get_current_time

logger = logging.getLogger(__name__)


def run_daily_insights_for_user(user):
    """
    Run scheduled insight checks for a single user.

    Generates a synthetic 'scheduled_check' event that triggers
    rules designed for periodic evaluation (missing logging, drop-offs, etc.).
    """
    event = {
        "event_type": "scheduled_check",
        "module": "all",
        "action": "scheduled_check",
        "timestamp_utc": get_current_time().isoformat(),
    }

    try:
        insights = run_insights(user, event)
        return insights
    except Exception as e:
        logger.error(
            f"Daily insights failed for user {user.id}: {e}", exc_info=True
        )
        return []


def run_daily_insights_all_users():
    """
    Run scheduled insight checks for all active users.

    Returns count of total insights generated.
    """
    from apps.users.models import User

    active_users = User.objects.filter(is_active=True)
    total_insights = 0

    for user in active_users:
        insights = run_daily_insights_for_user(user)
        total_insights += len(insights)

    return total_insights
