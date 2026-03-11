"""
Notification Engine — Rate-limited, non-spammy insight notifications.

Rules:
- Only notify on warning/critical OR high-confidence positive
- Max 3 notifications per day per user
- Never notify on low confidence or "needs more data"
- In-app only (Insights Inbox badge) for v1
"""

import logging
from datetime import timedelta

from apps.core.ai_insights.models import Insight
from apps.core.time.system_clock import get_current_time

logger = logging.getLogger(__name__)

MAX_NOTIFICATIONS_PER_DAY = 3


def maybe_notify(user, insight):
    """
    Decide whether to notify the user about an insight.

    Args:
        user: Django user instance.
        insight: Insight model instance.

    Returns:
        True if notification was sent (in-app badge updated).
    """
    # Only notify on warning/critical or high-confidence positive
    if insight.severity not in ("warning", "critical", "positive"):
        return False

    if insight.severity == "positive" and insight.confidence_score < 0.8:
        return False

    # Rate limit: max notifications per day
    today_start = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = Insight.objects.filter(
        user=user,
        notified_at__gte=today_start,
    ).count()

    from apps.core.ai_config import get_threshold

    max_notifications = get_threshold("max_notifications_per_day", MAX_NOTIFICATIONS_PER_DAY)
    if today_count >= max_notifications:
        logger.info(
            f"Rate limited: user {user.id} already has {today_count} "
            f"notifications today"
        )
        return False

    # Mark as notified (in-app badge)
    insight.notified_at = get_current_time()
    insight.save(update_fields=["notified_at", "updated_at"])

    logger.info(
        f"Insight notification for user {user.id}: "
        f"[{insight.severity}] {insight.title}"
    )

    return True
