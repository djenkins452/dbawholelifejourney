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
"""

import logging

logger = logging.getLogger(__name__)


def fire_intelligence(user, module, record_id=None, action="record_created"):
    """
    Fire the post-save intelligence chain for a user action.

    Runs: SAE state update → PIE insights → PRIE predictions (via PIE).
    All steps are isolated — failures never propagate to the caller.

    Args:
        user: Django User instance.
        module: Domain module string (health, journal, purpose, faith, etc.).
        record_id: Optional ID of the created/updated record.
        action: Action type string (default "record_created").
    """
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
