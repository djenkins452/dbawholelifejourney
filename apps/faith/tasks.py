# ==============================================================================
# File: apps/faith/tasks.py
# Project: Whole Life Journey - Django 5.x
# Description: Celery tasks for the Faith module.
# ==============================================================================
"""Faith Celery tasks.

`compute_faith_mirror` runs the heavy Mirror aggregation off the request path
and caches the result, so the Faith "Your walk" view only ever reads the cache.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="faith.compute_faith_mirror")
def compute_faith_mirror(user_id):
    """Compute + cache the First Light Mirror (spiritual biography) for a user."""
    from django.contrib.auth import get_user_model
    from apps.faith.first_light.mirror import compute_and_cache

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return
    try:
        compute_and_cache(user)
    except Exception:
        logger.warning("faith: Mirror computation failed for user=%s", user_id, exc_info=True)
