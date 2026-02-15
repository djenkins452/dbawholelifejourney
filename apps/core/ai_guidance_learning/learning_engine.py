"""
GLOE — Learning Engine.

Main entry point for updating user learning profiles from lifecycle events.
"""

import logging

from django.db.models import Avg, Count, Q

from apps.core.ai_guidance_learning.learning_calculator import calculate_responsiveness_score
from apps.core.ai_guidance_learning.learning_models import (
    GuidanceLearningEvent,
    GuidanceLearningProfile,
)

logger = logging.getLogger(__name__)


def update_learning_profile(user):
    """
    Update the guidance learning profile for a user.

    Recalculates aggregate metrics from all GuidanceLearningEvents
    and computes the new responsiveness_score.

    Args:
        user: Django User instance.

    Returns:
        GuidanceLearningProfile instance.
    """
    profile, created = GuidanceLearningProfile.objects.get_or_create(user=user)

    # Aggregate from events
    events = GuidanceLearningEvent.objects.filter(user=user)

    counts = events.aggregate(
        total=Count("id"),
        acknowledged=Count("id", filter=Q(event_type="acknowledged")),
        dismissed=Count("id", filter=Q(event_type="dismissed")),
        acted=Count("id", filter=Q(event_type="acted")),
    )

    avg_response = events.aggregate(
        avg_time=Avg("response_time_seconds")
    )["avg_time"] or 0.0

    # Also count total guidance items that were shown (seen = total unique items)
    total_seen = (
        events.values("guidance_item_id").distinct().count()
    )

    # Update profile
    profile.total_guidance_seen = total_seen
    profile.total_guidance_acknowledged = counts["acknowledged"]
    profile.total_guidance_dismissed = counts["dismissed"]
    profile.total_guidance_acted = counts["acted"]
    profile.avg_response_time_seconds = round(avg_response, 1)

    # Calculate score
    profile.responsiveness_score = calculate_responsiveness_score(profile)

    profile.save()

    logger.debug(
        f"GLOE: Updated profile for user {user.id}: "
        f"seen={total_seen}, acted={counts['acted']}, "
        f"score={profile.responsiveness_score:.4f}"
    )

    return profile


def get_responsiveness_score(user):
    """
    Get the current responsiveness score for a user.

    Returns 0.5 (neutral) if no profile exists.

    Args:
        user: Django User instance.

    Returns:
        float — responsiveness score (0.0-1.0).
    """
    try:
        profile = GuidanceLearningProfile.objects.get(user=user)
        return profile.responsiveness_score
    except GuidanceLearningProfile.DoesNotExist:
        return 0.5
