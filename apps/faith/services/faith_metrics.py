"""
Faith Metrics Service — Canonical faith domain metrics.

This is the single canonical source for faith metrics consumed by:
- PersonalAssistant._get_faith_state()
- Executive Briefing faith context
- Proactive check-in generators
- Any future faith-metric consumer

Architecture: Reads from SAE (Layer 3) as primary source, with direct
queries for today-specific and computed fields that SAE doesn't track.
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


def get_faith_metrics(user) -> dict:
    """Return canonical faith metrics for a user.

    Combines SAE state (unanswered_prayers, reading_streak, etc.) with
    today-specific engagement data and direct queries for fields SAE
    doesn't compute (answered_prayers_month, faith_milestones, total_prayers).

    Returns dict with keys matching PA's _get_faith_state() contract:
        active_prayers, answered_prayers_month, total_prayers,
        faith_milestones, active_reading_plans,
        reading_completed_today, faith_engaged_today,
        reading_streak, recent_prayer_titles.
    """
    from apps.core.utils import get_user_today
    from apps.core.execution.execution_truth_engine import get_execution_truth

    today = get_user_today(user)
    month_ago = today - timedelta(days=30)

    # ── SAE state (primary source for aggregate metrics) ──
    sae_faith = _get_sae_faith(user)

    # ── Today-specific engagement via Execution Truth Engine ──
    truth = get_execution_truth(user, today)
    faith_truth = truth['domains']['faith']

    # ── Direct queries for fields SAE doesn't track ──
    from apps.faith.models import FaithMilestone, PrayerRequest

    prayers = PrayerRequest.objects.filter(user=user)
    answered_month = prayers.filter(
        is_answered=True, answered_at__gte=month_ago,
    ).count()
    total_prayers = prayers.count()
    milestones = FaithMilestone.objects.filter(user=user).count()

    return {
        # From SAE (or fallback to direct query)
        'active_prayers': sae_faith.get('unanswered_prayers', 0) or prayers.filter(is_answered=False).count(),
        'active_reading_plans': sae_faith.get('active_reading_plans', 0),
        'reading_streak': sae_faith.get('reading_streak', 0),
        'recent_prayer_titles': sae_faith.get('recent_prayer_titles', []),
        # Direct queries (not in SAE)
        'answered_prayers_month': answered_month,
        'total_prayers': total_prayers,
        'faith_milestones': milestones,
        # Today-specific (from Execution Truth Engine — includes routine bridge)
        'reading_completed_today': faith_truth['bible_reading_completed'],
        'faith_engaged_today': faith_truth['prayer_completed'] or faith_truth['bible_reading_completed'],
    }


def _get_sae_faith(user) -> dict:
    """Read faith state from SAE. Returns empty dict if unavailable."""
    try:
        from apps.core.ai_state.models import UserState
        sae = UserState.objects.filter(user=user).first()
        if sae and sae.state_data:
            return sae.state_data.get('faith', {})
    except Exception:
        logger.warning("FAITH_SERVICE SAE read failed for user=%s", user.id, exc_info=True)
    return {}
