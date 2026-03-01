# ==============================================================================
# File: apps/ai/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Celery tasks for CoS readiness and keep-alive
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Celery Tasks

Provides keep-alive and readiness tasks for the Chief of Staff system.
These tasks run via Celery Beat to maintain CoS responsiveness for active users.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.ai.tasks.cos_keepalive_task",
    bind=True,
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=25,
    acks_late=True,
)
def cos_keepalive_task(self):
    """
    Keep CoS context warm for recently active users.

    Runs every 30 seconds via Celery Beat. Checks for users who have
    interacted in the last 5 minutes and refreshes their context cache.
    This prevents context rebuild latency on subsequent messages.

    Lightweight: only processes up to 5 users per cycle.
    Safe: read-only context builds, no LLM calls, no memory writes.
    """
    from apps.ai.readiness_cache import get_active_user_ids, prewarm_cos_context
    from apps.ai.readiness_telemetry import log_keepalive_cycle

    try:
        active_ids = get_active_user_ids()
        if not active_ids:
            return

        from django.contrib.auth import get_user_model
        User = get_user_model()

        refreshed = 0
        for user_id in active_ids[:5]:  # Cap at 5 per cycle
            try:
                user = User.objects.get(id=user_id)
                prewarm_cos_context(user)
                refreshed += 1
            except User.DoesNotExist:
                from apps.ai.readiness_cache import remove_active_user
                remove_active_user(user_id)
            except Exception:
                logger.debug(
                    "CoS keepalive: failed to refresh user %s", user_id
                )

        log_keepalive_cycle(len(active_ids), refreshed)

    except Exception as exc:
        logger.warning("CoS keepalive task failed: %s", exc)
        raise self.retry(exc=exc)
