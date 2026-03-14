# ==============================================================================
# File: apps/core/ai_eae/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Celery tasks for signal aggregation
# Created: 2026-03-14 (Architecture Evolution Phase 4)
# ==============================================================================
"""
EAE Celery Tasks — Signal Aggregation

Nightly task that computes and persists SignalSnapshot records for all active users.
"""

import logging
import time

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='core.compute_nightly_signals')
def compute_nightly_signals():
    """
    Nightly signal aggregation.

    Scheduled at 11:30 PM via CELERY_BEAT_SCHEDULE.
    Iterates all active users and computes daily signal snapshots.
    Individual user failures don't halt the batch.
    """
    from django.contrib.auth import get_user_model
    from apps.core.utils import get_user_today
    from apps.core.ai_eae.signal_aggregation import SignalAggregationService

    User = get_user_model()

    # Only process users who have logged in within the last 30 days
    from django.utils import timezone
    import datetime as dt
    cutoff = timezone.now() - dt.timedelta(days=30)

    active_users = User.objects.filter(
        last_login__gte=cutoff,
        is_active=True,
    )

    total_users = active_users.count()
    success_count = 0
    error_count = 0
    total_signals = 0

    logger.info(
        "Starting nightly signal aggregation for %d active users",
        total_users,
    )

    for user in active_users.iterator():
        try:
            today = get_user_today(user)
            signals = SignalAggregationService.compute_daily_signals(user, today)
            total_signals += len(signals)
            success_count += 1
        except Exception as e:
            error_count += 1
            logger.error(
                "Signal aggregation failed for user %s: %s",
                user.pk, e, exc_info=True,
            )

        # Brief pause between users to avoid DB pressure
        time.sleep(0.05)

    logger.info(
        "Nightly signal aggregation complete: %d users processed, "
        "%d signals generated, %d errors",
        success_count, total_signals, error_count,
    )

    return {
        'total_users': total_users,
        'success_count': success_count,
        'error_count': error_count,
        'total_signals': total_signals,
    }
