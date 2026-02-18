"""
Phase 4 CoS — Noise Budget Controls.

Caps insight generation to prevent user fatigue:
- Max insights per day per user
- Max insights per 6-hour window per user
- Cross-domain dedupe (prevent duplicate patterns within a window)

Applied in the insight engine AFTER rule evaluation, BEFORE persistence.
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Budget caps
MAX_INSIGHTS_PER_DAY = 12
MAX_INSIGHTS_PER_6H_WINDOW = 5
MAX_CROSS_DOMAIN_PER_DAY = 4

# Cross-domain rule prefix for identification
CROSS_DOMAIN_PREFIX = "cross_domain_"


def check_noise_budget(user, insight_data, rule):
    """
    Check if creating this insight would exceed noise budget.

    Args:
        user: Django User instance.
        insight_data: dict with insight fields (severity, dedupe_key, etc.)
        rule: The rule instance that produced this insight.

    Returns:
        (allowed: bool, reason: str or None)
    """
    try:
        from apps.core.ai_insights.models import Insight

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = now - timedelta(hours=6)

        # Critical insights always pass through
        if insight_data.get("severity") == "critical":
            return True, None

        # Cap 1: Daily limit
        daily_count = Insight.objects.filter(
            user=user,
            created_at__gte=today_start,
        ).count()

        if daily_count >= MAX_INSIGHTS_PER_DAY:
            return False, f"Daily cap reached ({MAX_INSIGHTS_PER_DAY})"

        # Cap 2: 6-hour window limit
        window_count = Insight.objects.filter(
            user=user,
            created_at__gte=window_start,
        ).count()

        if window_count >= MAX_INSIGHTS_PER_6H_WINDOW:
            return False, f"6h window cap reached ({MAX_INSIGHTS_PER_6H_WINDOW})"

        # Cap 3: Cross-domain daily limit
        rule_name = getattr(rule, "rule_name", "")
        if rule_name.startswith(CROSS_DOMAIN_PREFIX):
            cross_domain_count = Insight.objects.filter(
                user=user,
                created_at__gte=today_start,
                insight_type__startswith="cross_domain",
            ).count()

            # Also count types that match cross-domain patterns
            from apps.core.ai_insights.rules_cross_domain import CrossDomainRule
            if isinstance(rule, CrossDomainRule):
                if cross_domain_count >= MAX_CROSS_DOMAIN_PER_DAY:
                    return False, f"Cross-domain daily cap ({MAX_CROSS_DOMAIN_PER_DAY})"

        # Cap 4: Dedupe check — same insight_type in last 24h
        dedupe_key = insight_data.get("dedupe_key", "")
        if dedupe_key:
            existing = Insight.objects.filter(
                user=user,
                dedupe_key=dedupe_key,
            ).exclude(status="dismissed").exists()

            if existing:
                return False, f"Dedupe: {dedupe_key} already active"

    except Exception as e:
        logger.debug(f"Noise budget check failed (allowing): {e}")

    return True, None


def get_budget_status(user):
    """
    Get the current noise budget status for a user.

    Returns:
        dict with remaining counts and limits.
    """
    try:
        from apps.core.ai_insights.models import Insight

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = now - timedelta(hours=6)

        daily_count = Insight.objects.filter(
            user=user,
            created_at__gte=today_start,
        ).count()

        window_count = Insight.objects.filter(
            user=user,
            created_at__gte=window_start,
        ).count()

        cross_domain_count = Insight.objects.filter(
            user=user,
            created_at__gte=today_start,
            insight_type__startswith="cross_domain",
        ).count()

        return {
            "daily_used": daily_count,
            "daily_limit": MAX_INSIGHTS_PER_DAY,
            "daily_remaining": max(0, MAX_INSIGHTS_PER_DAY - daily_count),
            "window_6h_used": window_count,
            "window_6h_limit": MAX_INSIGHTS_PER_6H_WINDOW,
            "window_6h_remaining": max(0, MAX_INSIGHTS_PER_6H_WINDOW - window_count),
            "cross_domain_used": cross_domain_count,
            "cross_domain_limit": MAX_CROSS_DOMAIN_PER_DAY,
            "cross_domain_remaining": max(0, MAX_CROSS_DOMAIN_PER_DAY - cross_domain_count),
        }
    except Exception:
        return {}
