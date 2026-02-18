"""
PGE -- Guidance Engine.

Main entry point for proactive guidance generation.
Reads SAE state, PIE insights, PRIE predictions, then passes through
the selector → ranker → logger pipeline.

This engine does NOT execute actions. It evaluates existing intelligence
and surfaces the most important items for the user to see.
"""

import logging

from django.utils import timezone

from apps.core.ai_guidance.guidance_ranker import rank_guidance
from apps.core.ai_guidance.guidance_selector import select_guidance

logger = logging.getLogger(__name__)


def generate_guidance(user):
    """
    Generate proactive guidance for a user.

    Pipeline: SAE state + PIE insights + PRIE predictions
              → select_guidance() → rank_guidance() → log_guidance()

    Args:
        user: Django user instance.

    Returns:
        List of GuidanceItem instances (created or updated).
    """
    try:
        # Step 1: Gather inputs from intelligence engines
        state = _get_user_state(user)
        insights = _get_recent_insights(user)
        predictions = _get_active_predictions(user)

        # Step 2: Select guidance candidates via rules
        candidates = select_guidance(user, state, insights, predictions)

        if not candidates:
            logger.debug(f"PGE: No guidance candidates for user {user.id}")
            return []

        # Step 3: Rank and limit (GLOE responsiveness applied if available)
        ranked = rank_guidance(candidates, user=user)

        # Step 3.5: ICQG quality gate (non-blocking)
        try:
            from apps.core.ai_quality.quality_gate import filter_guidance_candidates
            ranked = filter_guidance_candidates(user, ranked)
        except Exception as e:
            logger.warning(f"PGE: ICQG filter failed (continuing): {e}")

        # Step 4: Store with deduplication
        from apps.core.ai_guidance.guidance_logger import log_guidance

        stored = log_guidance(user, ranked)

        logger.info(
            f"PGE: Generated {len(stored)} guidance items for user {user.id}"
        )
        return stored

    except Exception as e:
        logger.error(
            f"PGE: Guidance generation failed for user {user.id}: {e}",
            exc_info=True,
        )
        return []


def get_active_guidance(user, limit=5):
    """
    Retrieve active guidance items for a user, sorted by priority.

    Excludes:
    - Inactive items (is_active=False)
    - Expired items (expires_at in the past)
    - Dismissed items (dismissed_at is set)
    - Currently snoozed items (snoozed_until in the future)

    Args:
        user: Django user instance.
        limit: Maximum items to return.

    Returns:
        QuerySet of active GuidanceItem instances.
    """
    from apps.core.ai_guidance.models import GuidanceItem

    now = timezone.now()

    return (
        GuidanceItem.objects.filter(
            user=user,
            is_active=True,
            dismissed_at__isnull=True,
        )
        .exclude(expires_at__lt=now)
        .exclude(snoozed_until__gt=now)
        .order_by("priority", "-created_at")[:limit]
    )


def expire_old_guidance():
    """
    Deactivate guidance items that have passed their expiry date.

    Called by the scheduler. Safe to run frequently.
    """
    from apps.core.ai_guidance.models import GuidanceItem

    now = timezone.now()
    expired = GuidanceItem.objects.filter(
        is_active=True,
        expires_at__lt=now,
    ).update(is_active=False)

    if expired:
        logger.info(f"PGE: Expired {expired} guidance items")
    return expired


# ---------------------------------------------------------------------------
# Internal helpers — ImportError-guarded engine reads
# ---------------------------------------------------------------------------


def _get_user_state(user):
    """
    Read SAE user state. Failures never break PGE.
    Returns dict or empty dict.
    """
    try:
        from apps.core.ai_state.state_engine import get_user_state

        state = get_user_state(user)
        return state or {}
    except ImportError:
        logger.debug("SAE not available, using empty state")
        return {}
    except Exception as e:
        logger.error(f"PGE: SAE read failed: {e}", exc_info=True)
        return {}


def _get_recent_insights(user):
    """
    Read recent PIE insights. Failures never break PGE.
    Returns QuerySet or empty list.
    """
    try:
        from apps.core.ai_insights.models import Insight

        return Insight.objects.filter(
            user=user,
        ).exclude(status="dismissed").order_by("-created_at")
    except ImportError:
        logger.debug("PIE not available, using empty insights")
        return []
    except Exception as e:
        logger.error(f"PGE: PIE read failed: {e}", exc_info=True)
        return []


def _get_active_predictions(user):
    """
    Read active PRIE predictions. Failures never break PGE.
    Returns QuerySet or empty list.
    """
    try:
        from apps.core.ai_predictions.models import Prediction

        return Prediction.objects.filter(
            user=user,
            status="active",
        ).order_by("-created_at")
    except ImportError:
        logger.debug("PRIE not available, using empty predictions")
        return []
    except Exception as e:
        logger.error(f"PGE: PRIE read failed: {e}", exc_info=True)
        return []
