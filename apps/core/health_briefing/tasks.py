"""
HealthBriefing background tasks (Phase 1A · C12).

Two tasks, both ``@shared_task`` so they register with the project's
Celery app via the auto-imported `tasks.py` pattern. Imported from
``apps/core/apps.py:ready()`` so registration happens at Django boot
without depending on health_briefing being a separate INSTALLED_APP.

* ``recompute_health_briefing_for_user_task(user_id)`` — composes one
  user's briefing and persists the snapshot. Idempotent: identical SAE
  state produces an identical briefing_id (composer's evidence hash),
  so multiple rapid dispatches collapse via the snapshot's
  ``unique=True`` briefing_id and ``update_or_create`` upsert.

* ``recompute_all_health_briefings_task()`` — Celery-Beat-driven
  scheduler. Iterates users who have an existing SAE UserState and
  dispatches the per-user task asynchronously. Avoids touching users
  who have never built any state (cold accounts).

**Wave 3 invariant:** these tasks call the composer, which writes to
HealthBriefingSnapshot only. They do NOT touch CoS context, Beth
prompts, or any narration path. Beth integration is W5.

Recompute boundedness (Wave 3 guardrail):

* Signal handlers (`signals.py`) call `.delay()` only — never invoke
  the composer synchronously, so an ingestion save is never blocked.
* HealthBriefingSnapshot has zero post_save / post_delete handlers
  (verified C4). Recomputes do not cascade.
* The composer reads SAE state read-only and does not mutate any
  domain model. No write → recompute → write loop possible.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth import get_user_model


logger = logging.getLogger(__name__)


@shared_task(
    name="apps.core.health_briefing.tasks.recompute_health_briefing_for_user_task",
    ignore_result=True,
    # Cap retries low — composer is deterministic; a transient SAE
    # read failure should resolve on the next 30-min beat tick.
    max_retries=2,
    default_retry_delay=60,
)
def recompute_health_briefing_for_user_task(user_id: int) -> str:
    """Compose + persist the HealthBriefing for one user.

    Returns the briefing_id (or "skipped:<reason>") for log inspection.
    """
    from apps.core.health_briefing.composer import compose_briefing

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.info(
            "[HEALTH_BRIEFING] recompute skipped — user_id=%s not found", user_id,
        )
        return f"skipped:user_not_found:{user_id}"

    try:
        briefing = compose_briefing(user, persist=True)
    except Exception:
        logger.error(
            "[HEALTH_BRIEFING] recompute failed for user_id=%s", user_id,
            exc_info=True,
        )
        raise
    logger.info(
        "[HEALTH_BRIEFING] recomputed user_id=%s briefing_id=%s status=%s",
        user_id, briefing.briefing_id[:12], briefing.overall_status.value,
    )
    return briefing.briefing_id


@shared_task(
    name="apps.core.health_briefing.tasks.recompute_all_health_briefings_task",
    ignore_result=True,
)
def recompute_all_health_briefings_task() -> int:
    """Scheduled (every 30 minutes via CELERY_BEAT_SCHEDULE).

    Iterates users with an existing SAE UserState and dispatches the
    per-user recompute task asynchronously. Returns the dispatch count
    for log inspection.
    """
    from apps.core.ai_state.models import UserState

    user_ids = list(
        UserState.objects.values_list("user_id", flat=True).distinct()
    )
    dispatched = 0
    for uid in user_ids:
        recompute_health_briefing_for_user_task.delay(uid)
        dispatched += 1
    logger.info(
        "[HEALTH_BRIEFING] scheduled recompute fan-out dispatched=%d", dispatched,
    )
    return dispatched
