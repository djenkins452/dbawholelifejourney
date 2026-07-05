"""SAE warm tasks — Phase 3 of the dashboard-latency project.

The Phase 3 architecture moves SAE rebuilds off the request path.
Dashboard reads SAE state with ``allow_rebuild=False`` (see
``apps.core.ai_state.state_engine.get_user_state``). When the snapshot
is stale or missing, the request enqueues one of these background
tasks so the *next* render finds warm data.

Two tasks:

  - ``deferred_warm_sae_module(user_id, module)`` —
    Rebuild a SINGLE module via ``state_updater.update_user_state``.
    Cheap (one builder, ~10–50 queries). Used by domain-write
    subscribers (journal, task, faith, purpose) and by the dashboard
    read-only path as a follow-up "catch up next time" trigger.

  - ``deferred_rebuild_full_sae(user_id)`` —
    Full ``rebuild_user_state`` (~600 queries). Used sparingly: only
    when SAE state is entirely missing for a user (brand-new user;
    after Learning Mode exit; admin reseed).

Both are idempotent: ``update_user_state`` / ``rebuild_user_state``
each save_or_update the same ``UserState`` row, so concurrent enqueues
either coalesce harmlessly or replace each other's last-writer.

Fail-safe: tasks log warning + return — they NEVER re-raise into the
caller. A failed warm leaves SAE stale; the next domain write or the
nightly SAME-cycle worker recovers.
"""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger("celery.tasks")


@shared_task(
    name="ai_state.deferred_warm_sae_module",
    bind=True,
    max_retries=1,
    soft_time_limit=30,
    time_limit=45,
    acks_late=True,
)
def deferred_warm_sae_module(self, user_id, module):
    """Rebuild ONE SAE module off the request path.

    Args:
        user_id: User PK.
        module: Canonical module name (e.g. ``"health"``, ``"faith"``).
    """
    from django.contrib.auth import get_user_model

    from apps.core.ai_state.state_updater import update_user_state

    User = get_user_model()
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return {"status": "user_not_found", "user_id": user_id, "module": module}

    try:
        update_user_state(user, module)
        return {"status": "ok", "user_id": user_id, "module": module}
    except SoftTimeLimitExceeded:
        logger.warning(
            "deferred_warm_sae_module soft-time-limit: user=%s module=%s",
            user_id, module,
        )
        return {"status": "soft_timeout", "user_id": user_id, "module": module}
    except Exception as exc:
        logger.warning(
            "deferred_warm_sae_module failed: user=%s module=%s",
            user_id, module, exc_info=True,
        )
        # Single retry, then give up — next domain write will re-enqueue.
        try:
            raise self.retry(exc=exc, countdown=20)
        except Exception:
            return {"status": "failed", "user_id": user_id, "module": module}


@shared_task(
    name="ai_state.deferred_rebuild_full_sae",
    bind=True,
    max_retries=1,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def deferred_rebuild_full_sae(self, user_id):
    """Full SAE rebuild — all ~25 modules. Heavy. Use sparingly.

    Called only when dashboard read-only path observes an entirely
    empty state_data and the user has no other warm-task expected to
    fire soon.
    """
    from django.contrib.auth import get_user_model

    from apps.core.ai_state.state_engine import rebuild_user_state

    User = get_user_model()
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return {"status": "user_not_found", "user_id": user_id}

    try:
        rebuild_user_state(user)
        return {"status": "ok", "user_id": user_id}
    except SoftTimeLimitExceeded:
        logger.warning(
            "deferred_rebuild_full_sae soft-time-limit: user=%s", user_id,
        )
        return {"status": "soft_timeout", "user_id": user_id}
    except Exception as exc:
        logger.warning(
            "deferred_rebuild_full_sae failed: user=%s", user_id, exc_info=True,
        )
        try:
            raise self.retry(exc=exc, countdown=30)
        except Exception:
            return {"status": "failed", "user_id": user_id}


def enqueue_module_warm(user, module):
    """Safe wrapper to enqueue a single-module SAE warm task.

    Use from request-path consumers (e.g. dashboard composer) to
    schedule a background catch-up. Fail-safe: never raises into the
    caller. When Celery is unavailable / EAGER is on, behavior is the
    Celery default (sync execute in EAGER mode, log+ignore otherwise).
    """
    if not getattr(user, "is_authenticated", False):
        return
    from apps.core.celery_utils import safe_enqueue
    safe_enqueue(deferred_warm_sae_module, user.id, module)


def enqueue_full_sae_warm(user):
    """Safe wrapper for full SAE rebuild — see deferred_rebuild_full_sae.

    Use from the dashboard read-only path when state_data is entirely
    empty (brand-new user; first ever render). Fail-safe and non-blocking:
    routed through safe_enqueue so a degraded broker can never block the
    request thread.
    """
    if not getattr(user, "is_authenticated", False):
        return
    from apps.core.celery_utils import safe_enqueue
    safe_enqueue(deferred_rebuild_full_sae, user.id)
