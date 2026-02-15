"""
DNE — Delivery Logger.

Logs skipped deliveries for audit and debugging.
"""

import logging

from django.db import IntegrityError

from apps.core.ai_delivery.models import DeliveredNotification

logger = logging.getLogger(__name__)


def log_skip(user, channel, source_engine, source_object_type, source_object_id,
             payload, skip_reason):
    """
    Log a skipped delivery attempt.

    Returns:
        DeliveredNotification or None.
    """
    dedupe_hash = DeliveredNotification.compute_dedupe_hash(
        user.id, channel, source_engine, source_object_type, source_object_id,
    )

    try:
        record = DeliveredNotification.objects.create(
            user=user,
            source_engine=source_engine,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            channel=channel,
            title=payload.get("title", ""),
            message=payload.get("message", ""),
            action_url=payload.get("action_url", ""),
            status=DeliveredNotification.STATUS_SKIPPED,
            skip_reason=skip_reason,
            dedupe_hash=dedupe_hash,
        )

        logger.debug(
            f"DNE: Skipped {channel} for user {user.id}: "
            f"{source_engine}/{source_object_type}/{source_object_id} "
            f"reason={skip_reason}"
        )
        return record

    except IntegrityError:
        # Already logged (dedupe hash conflict) — ignore
        return None
    except Exception as e:
        logger.error(f"DNE: Failed to log skip: {e}")
        return None
