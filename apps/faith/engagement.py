"""
Faith engagement tracking utility.

Centralizes the check for whether a user has engaged with faith today.
Engagement sources:
  1. Completed a reading plan day today (existing UserReadingProgress)
  2. Completed a faith-linked task today (Task with module='faith')
"""
import logging
from datetime import date
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def is_faith_engaged_today(user, today: Optional[date] = None) -> bool:
    """
    Check if user has engaged with faith today via any channel.

    Args:
        user: Django User instance
        today: Date to check (defaults to user's timezone today)

    Returns:
        True if any faith engagement detected today
    """
    if today is None:
        from apps.core.utils import get_user_today
        today = get_user_today(user)

    return (
        _reading_completed_today(user, today)
        or _faith_task_completed_today(user, today)
    )


def get_faith_engagement_details(user, today: Optional[date] = None) -> Dict:
    """
    Get detailed faith engagement state for today.

    Returns dict with:
        reading_completed_today: bool
        faith_task_completed_today: bool
        faith_engaged_today: bool (OR of above)
    """
    if today is None:
        from apps.core.utils import get_user_today
        today = get_user_today(user)

    reading = _reading_completed_today(user, today)
    task = _faith_task_completed_today(user, today)

    return {
        'reading_completed_today': reading,
        'faith_task_completed_today': task,
        'faith_engaged_today': reading or task,
    }


def _reading_completed_today(user, today: date) -> bool:
    """Check if user completed a reading plan day today."""
    try:
        from apps.faith.models import UserReadingPlan, UserReadingProgress
        active_plans = UserReadingPlan.objects.filter(
            user=user, plan_status='active'
        ).exclude(status='deleted')
        if not active_plans.exists():
            return False
        return UserReadingProgress.objects.filter(
            user_plan__in=active_plans,
            is_completed=True,
            completed_at__date=today,
        ).exists()
    except Exception:
        logger.exception("Error checking reading completion")
        return False


def _faith_task_completed_today(user, today: date) -> bool:
    """Check if user completed a faith-linked task today."""
    try:
        from apps.life.models import Task
        return Task.objects.filter(
            user=user,
            module='faith',
            is_completed=True,
            completed_at__date=today,
        ).exists()
    except Exception:
        logger.exception("Error checking faith task completion")
        return False
