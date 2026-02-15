"""
GLOE — Learning Logger.

Records individual guidance lifecycle events and triggers profile updates.
"""

import logging

from django.utils import timezone

from apps.core.ai_guidance_learning.learning_models import (
    GuidanceLearningEvent,
    GuidanceLearningProfile,
)

logger = logging.getLogger(__name__)


def log_learning_event(user, guidance_item, event_type):
    """
    Log a guidance lifecycle event for learning.

    Called when a user acknowledges, dismisses, or acts on guidance.
    Calculates response time from guidance creation to event.
    Then triggers a profile update.

    Args:
        user: Django User instance.
        guidance_item: GuidanceItem instance.
        event_type: str — "acknowledged", "dismissed", or "acted".

    Returns:
        GuidanceLearningEvent instance.
    """
    now = timezone.now()

    # Calculate response time
    response_time = (now - guidance_item.created_at).total_seconds()
    response_time = max(0, response_time)  # Safety clamp

    event = GuidanceLearningEvent.objects.create(
        user=user,
        guidance_item=guidance_item,
        event_type=event_type,
        response_time_seconds=response_time,
    )

    logger.debug(
        f"GLOE: Logged {event_type} event for user {user.id}, "
        f"guidance {guidance_item.id}, response_time={response_time:.0f}s"
    )

    # Trigger async-safe profile update
    try:
        from apps.core.ai_guidance_learning.learning_engine import update_learning_profile
        update_learning_profile(user)
    except Exception as e:
        logger.error(f"GLOE: Profile update failed for user {user.id}: {e}")

    return event
