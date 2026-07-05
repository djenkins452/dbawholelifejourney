"""
Intelligence Hook — Lightweight post-save trigger for Django views.

Allows regular Django form views (non-UAIO) to fire the intelligence
chain (SAE → PIE → PRIE) after creating or updating records.

Usage in a view's form_valid():

    from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence

    def form_valid(self, form):
        response = super().form_valid(form)
        fire_intelligence(self.request.user, "health", self.object.id)
        return response

REQUEST-PATH SAFETY (2026-07-05):
    ``fire_intelligence`` is called from `form_valid()` across health, journal,
    purpose, faith, meals, and the mobile HealthKit ingest endpoint. Its chain
    runs `update_user_state` (the ~69-query health SAE builder) + a full
    `run_insights` pass — heavy work that MUST NOT run on the request thread.
    So `fire_intelligence` now ENQUEUES the chain (fire-and-forget via
    safe_enqueue) and returns immediately. The synchronous chain lives in
    `run_intelligence_chain` for the Celery worker (and any genuine background
    caller). Under CELERY_TASK_ALWAYS_EAGER (tests) the enqueue runs inline, so
    tests still observe insights/state synchronously after a write.
"""

import logging

logger = logging.getLogger(__name__)


def fire_intelligence(user, module, record_id=None, action="record_created"):
    """
    Enqueue the post-save intelligence chain — NON-BLOCKING (request-path safe).

    Hands the SAE → PIE → PRIE chain to a Celery worker via ``safe_enqueue`` so
    the request thread never runs the heavy `update_user_state` + `run_insights`
    work. Returns immediately; if the broker is unavailable the enqueue is
    skipped (the periodic SAME cycle + the post_save `_defer_sae_refresh` signal
    keep SAE state fresh regardless).

    Args:
        user: Django User instance.
        module: Domain module string (health, journal, purpose, faith, etc.).
        record_id: Optional ID of the created/updated record.
        action: Action type string (default "record_created").
    """
    if user is None or not getattr(user, "id", None):
        return
    from apps.core.celery_utils import safe_enqueue
    from apps.core.tasks import deferred_fire_intelligence
    safe_enqueue(deferred_fire_intelligence, user.id, module, record_id, action)


def run_intelligence_chain(user, module, record_id=None, action="record_created"):
    """
    Run the post-save intelligence chain SYNCHRONOUSLY.

    Runs: SAE state update → PIE insights → PRIE predictions (via PIE).
    All steps are isolated — failures never propagate to the caller.

    This is the worker-side body executed by ``deferred_fire_intelligence``.
    Do NOT call this directly from a request path — use ``fire_intelligence``
    (which enqueues it). Heavy: `update_user_state` for the `health` module is
    the ~69-query builder, and `run_insights` evaluates every registered rule.
    """
    from apps.core.ai_observability.trace import trace_context

    with trace_context(source="intelligence_hook"):
        # Step 1: SAE state update
        try:
            from apps.core.ai_state.state_updater import update_user_state

            update_user_state(user, module, record_id)
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Intelligence hook SAE failed for user {user.id}: {e}")

        # Step 2: PIE insights (which internally triggers PRIE predictions)
        try:
            from django.conf import settings as django_settings

            if not getattr(django_settings, "AI_INSIGHTS_ENABLED", True):
                return

            import apps.core.ai_insights.rules_health  # noqa: F401
            import apps.core.ai_insights.rules_body_composition  # noqa: F401
            import apps.core.ai_insights.rules_goals  # noqa: F401
            import apps.core.ai_insights.rules_habits  # noqa: F401
            import apps.core.ai_insights.rules_journal  # noqa: F401
            import apps.core.ai_insights.rules_transformation  # noqa: F401
            import apps.core.ai_insights.rules_first_entry  # noqa: F401
            import apps.core.ai_insights.rules_tasks  # noqa: F401
            import apps.core.ai_insights.rules_behavior  # noqa: F401
            import apps.core.ai_insights.rules_context  # noqa: F401
            import apps.core.ai_insights.health.sleep_analysis  # noqa: F401

            from apps.core.ai_insights.insight_engine import run_insights
            from apps.core.time.system_clock import get_current_time

            event = {
                "event_type": "record_created",
                "module": module,
                "action": action,
                "record_id": record_id,
                "timestamp_utc": get_current_time().isoformat(),
            }

            run_insights(user, event)

        except Exception as e:
            logger.error(f"Intelligence hook PIE failed for user {user.id}: {e}")
