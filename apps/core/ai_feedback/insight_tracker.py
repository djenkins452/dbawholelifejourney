"""
Phase 4 CoS — Insight Engagement Tracker.

Tracks if user views/acts/dismisses insights.
Feeds weight adjustments into PIE ranking.

Public API:
    - record_insight_engagement(user, insight, event_type) -> InsightEngagement
    - get_insight_engagement_profile(user) -> InsightEngagementProfile
    - get_insight_type_weights(user) -> dict
"""

import logging

from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.core.ai_feedback.models import (
    InsightEngagement,
    InsightEngagementProfile,
)

logger = logging.getLogger(__name__)


def record_insight_engagement(user, insight, event_type):
    """
    Record a user's engagement with an insight.

    Args:
        user: Django User instance.
        insight: Insight model instance.
        event_type: "viewed" | "acted" | "dismissed"

    Returns:
        InsightEngagement instance.
    """
    engagement = InsightEngagement.objects.create(
        user=user,
        insight=insight,
        event_type=event_type,
    )

    # Update insight status to match
    if event_type == "viewed" and insight.status == "new":
        insight.status = "read"
        insight.save(update_fields=["status", "updated_at"])
    elif event_type == "dismissed":
        insight.status = "dismissed"
        insight.save(update_fields=["status", "updated_at"])

    # Update aggregate profile
    _update_engagement_profile(user)

    return engagement


def get_insight_engagement_profile(user):
    """Get or create the user's insight engagement profile."""
    profile, _ = InsightEngagementProfile.objects.get_or_create(user=user)
    return profile


def get_insight_type_weights(user):
    """
    Compute per-insight_type engagement weights.

    Higher weight = user engages more with this type → surface it more.
    Lower weight = user dismisses this type → deprioritize.

    Returns:
        dict: {insight_type: weight_float} where weight is 0.0-2.0
    """
    try:
        from apps.core.ai_insights.models import Insight

        # Get engagement stats by insight_type
        stats = (
            InsightEngagement.objects.filter(user=user)
            .values("insight__insight_type")
            .annotate(
                total=Count("id"),
                acted=Count("id", filter=Q(event_type="acted")),
                dismissed=Count("id", filter=Q(event_type="dismissed")),
                viewed=Count("id", filter=Q(event_type="viewed")),
            )
        )

        weights = {}
        for stat in stats:
            itype = stat["insight__insight_type"]
            total = stat["total"]
            if total == 0:
                continue

            # Weight formula: acted boosts, dismissed penalizes
            acted_ratio = stat["acted"] / total
            dismissed_ratio = stat["dismissed"] / total
            weight = 1.0 + (acted_ratio * 0.5) - (dismissed_ratio * 0.5)
            weights[itype] = round(max(0.2, min(2.0, weight)), 2)

        return weights

    except Exception as e:
        logger.debug(f"InsightTracker: Could not compute weights: {e}")
        return {}


def _update_engagement_profile(user):
    """Update the aggregate engagement profile."""
    profile, _ = InsightEngagementProfile.objects.get_or_create(user=user)

    stats = InsightEngagement.objects.filter(user=user).aggregate(
        total_viewed=Count("id", filter=Q(event_type="viewed")),
        total_acted=Count("id", filter=Q(event_type="acted")),
        total_dismissed=Count("id", filter=Q(event_type="dismissed")),
    )

    total = (
        (stats["total_viewed"] or 0)
        + (stats["total_acted"] or 0)
        + (stats["total_dismissed"] or 0)
    )

    profile.total_viewed = stats["total_viewed"] or 0
    profile.total_acted = stats["total_acted"] or 0
    profile.total_dismissed = stats["total_dismissed"] or 0
    profile.total_insights_shown = total

    if total > 0:
        # Engagement = (viewed + 2*acted) / (total + dismissed)
        numerator = profile.total_viewed + (2 * profile.total_acted)
        denominator = total + profile.total_dismissed
        profile.engagement_score = round(
            min(1.0, numerator / max(denominator, 1)), 4
        )

    # Determine preferred severity
    try:
        preferred = (
            InsightEngagement.objects.filter(user=user, event_type="acted")
            .values("insight__severity")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )
        if preferred:
            profile.preferred_severity = preferred["insight__severity"]
    except Exception:
        pass

    profile.save()
