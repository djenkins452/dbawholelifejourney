"""
Dashboard V2 Celery tasks for nightly computations.

Tasks:
- compute_nightly_momentum: Persist GoalMomentumSnapshot for all users
- detect_celebrations: Run celebration detection for all users
- expire_celebrations: Expire old unrevealed celebrations
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="dashboard_v2.compute_nightly_momentum")
def compute_nightly_momentum():
    """
    Compute and persist momentum snapshots for all active users.
    Scheduled to run at 2:30 AM (after SAE and PRIE complete).
    """
    from django.conf import settings

    User = settings.AUTH_USER_MODEL
    from django.contrib.auth import get_user_model

    UserModel = get_user_model()

    users = UserModel.objects.filter(is_active=True)
    success_count = 0
    error_count = 0

    for user in users.iterator():
        try:
            from apps.dashboard_v2.services.momentum_service import GoalMomentumService

            service = GoalMomentumService(user)
            service.compute_and_persist()
            success_count += 1
        except Exception:
            error_count += 1
            logger.error(
                "Momentum computation failed for user %s", user.pk, exc_info=True
            )

    logger.info(
        "Nightly momentum: %d succeeded, %d failed", success_count, error_count
    )


@shared_task(name="dashboard_v2.detect_celebrations")
def detect_celebrations():
    """
    Run celebration detection for all active users.
    Scheduled to run at 3:00 AM (after momentum snapshots).
    """
    from django.contrib.auth import get_user_model

    UserModel = get_user_model()
    users = UserModel.objects.filter(is_active=True)
    count = 0

    for user in users.iterator():
        try:
            from apps.dashboard_v2.services.celebration_service import (
                CelebrationDetectionService,
            )

            service = CelebrationDetectionService(user)
            service.detect_and_store()
            count += 1
        except Exception:
            logger.error(
                "Celebration detection failed for user %s", user.pk, exc_info=True
            )

    logger.info("Celebration detection completed for %d users", count)


@shared_task(name="dashboard_v2.expire_celebrations")
def expire_celebrations():
    """
    Expire PreparedCelebrations past their expires_at timestamp.
    Scheduled to run at 4:00 AM.
    """
    from apps.dashboard_v2.models import PreparedCelebration

    expired_count = PreparedCelebration.objects.filter(
        celebration_status="ready",
        expires_at__lte=timezone.now(),
    ).update(celebration_status="expired")

    if expired_count:
        logger.info("Expired %d celebrations", expired_count)
