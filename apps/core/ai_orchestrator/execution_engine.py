"""
Execution Engine — Central execution authority for all AI-initiated actions.

This is the SINGLE execution gateway for the orchestrator pipeline.
All AI-initiated database writes and intelligence chain triggers flow through
execute_action(). The intelligence chain runs post-execution:

    Safety → Execute → SAE (future) → PIE → PRIE

No intelligence trigger (insights, predictions, state updates) may bypass
this function.
"""

import logging
import time as _time

from apps.core.ai_orchestrator.safety_engine import validate_action

logger = logging.getLogger(__name__)


def _record_aafr(user, intent_type, outcome, error_category="", start_time=None):
    """Record an AI action metric (AAFR). Never raises — telemetry must not block execution."""
    try:
        from apps.core.ai_observability.models import AIActionMetric

        duration_ms = int((_time.monotonic() - start_time) * 1000) if start_time else 0
        AIActionMetric.objects.create(
            intent_type=intent_type or "unknown",
            outcome=outcome,
            error_category=error_category or "",
            duration_ms=duration_ms,
            user_id=user.id if user else None,
        )
    except Exception as e:
        logger.debug("AAFR recording failed (non-blocking): %s", e)


def execute_action(user, enriched_action):
    """
    Execute an enriched action and run the intelligence chain.

    This is the SINGLE execution authority. All AI-initiated actions
    flow through here. Post-execution, the intelligence chain fires:

    1. Learning Mode gate (blocks all execution)
    2. Safety validation
    3. Delegate to existing execute_intent
    4. Intelligence chain (on success):
       a. State Awareness Engine (future — SAE placeholder)
       b. Proactive Insight Engine (PIE)
       c. Predictive Intelligence Engine (PRIE, triggered by PIE)

    Args:
        user: Django user instance.
        enriched_action: EnrichedAction from action_router.

    Returns:
        ActionResult from the existing intent service, or None on safety failure.
    """
    from apps.ai.intent_service import IntentResult, intent_service

    _aafr_start = _time.monotonic()

    # Step 0: Learning Mode gate — block domain execution
    # Control-plane intents (enter/exit learning mode) always bypass this gate.
    LEARNING_MODE_CONTROL_INTENTS = {'enter_learning_mode', 'exit_learning_mode'}
    try:
        from apps.core.blueprint.learning_mode import is_learning_mode_active
        if (is_learning_mode_active(user)
                and enriched_action.intent_type not in LEARNING_MODE_CONTROL_INTENTS):
            from apps.ai.intent_service import ActionResult
            logger.info(
                "UAIO execution blocked (Learning Mode active): %s for user %s",
                enriched_action.intent_type, user.id,
            )
            _record_aafr(user, enriched_action.intent_type, 'blocked', 'learning_mode_active', _aafr_start)
            return ActionResult(
                success=False,
                message=(
                    "Learning Mode is active.\n"
                    "I'm listening and learning right now, not executing actions.\n"
                    "When you're ready, exit Learning Mode and I'll begin taking action."
                ),
                error='learning_mode_active',
                action_type=enriched_action.intent_type,
            )
    except ImportError:
        pass  # Learning Mode module not installed — expected
    except Exception as e:
        logger.error(
            "Learning Mode check CRITICAL FAILURE in execution_engine "
            "(blocking execution for safety): %s", e, exc_info=True,
        )
        from apps.ai.intent_service import ActionResult
        _record_aafr(user, enriched_action.intent_type, 'failure', 'learning_mode_check_failed', _aafr_start)
        return ActionResult(
            success=False,
            message="Unable to verify safety state. Please try again.",
            error='learning_mode_check_failed',
            action_type=enriched_action.intent_type,
        )

    # Step 1: Safety check
    safety_result = validate_action(enriched_action)
    if not safety_result.is_safe:
        logger.warning(
            f"Action blocked by safety engine: {enriched_action.intent_type} - "
            f"{safety_result.reason}"
        )
        from apps.ai.intent_service import ActionResult

        _record_aafr(user, enriched_action.intent_type, 'blocked', 'safety_blocked', _aafr_start)
        return ActionResult(
            success=False,
            message=safety_result.user_message,
            error=safety_result.reason,
            action_type=enriched_action.intent_type,
        )

    # Step 2: Build IntentResult compatible with existing execute_intent
    # Filter out internal orchestrator keys (prefixed with _)
    clean_params = {
        k: v
        for k, v in enriched_action.parameters.items()
        if not k.startswith("_")
    }

    intent_result = IntentResult(
        intent_type=enriched_action.intent_type,
        parameters=clean_params,
    )

    # Step 3: Delegate to existing handler
    try:
        result = intent_service.execute_intent(intent_result, user)
    except Exception as e:
        logger.error(
            f"Execution error for {enriched_action.intent_type}: {e}",
            exc_info=True,
        )
        from apps.ai.intent_service import ActionResult

        _record_aafr(user, enriched_action.intent_type, 'failure', 'internal_error', _aafr_start)
        return ActionResult(
            success=False,
            message="Sorry, I couldn't complete that action.",
            error='internal_error',
            action_type=enriched_action.intent_type,
        )

    # Step 4: Invalidate CoS context cache so next message sees fresh state
    if result and result.success:
        try:
            from apps.ai.readiness_cache import invalidate_cos_context
            invalidate_cos_context(user)
        except Exception:
            pass  # Cache invalidation is best-effort

    # Step 5: Intelligence chain (only on successful execution)
    if result and result.success:
        _run_intelligence_chain(user, enriched_action, result)

    # AAFR telemetry — record final outcome
    if result:
        _record_aafr(
            user, enriched_action.intent_type,
            'success' if result.success else 'failure',
            result.error or "" if not result.success else "",
            _aafr_start,
        )

    return result


def _run_intelligence_chain(user, enriched_action, action_result):
    """
    Post-execution intelligence chain.

    Runs sequentially after every successful action:
    1. State Awareness Engine (future — SAE)
    2. Proactive Insight Engine (PIE)
    3. Predictive Intelligence Engine (PRIE, triggered by PIE internally)

    Each step is isolated — failures never break the chain or the user flow.
    """
    module = enriched_action.module
    record_id = (
        action_result.created_object.get("id")
        if action_result.created_object
        else None
    )

    # ── Step 1: State Awareness Engine (future) ──────────────────
    # SAE will plug in here when installed. Import-guarded so
    # the system works with or without SAE present.
    try:
        from apps.core.ai_state.state_updater import update_user_state  # noqa: F401

        update_user_state(user, module, record_id)
    except ImportError:
        pass  # SAE not yet installed — expected
    except Exception as e:
        logger.error(f"SAE update failed for user {user.id}: {e}", exc_info=True)

    # ── Step 2: CoS Blueprint Awareness ─────────────────────────
    # For scheduling actions (create_event, create_task), recompute
    # the architecture plan so CoS context stays current.
    if enriched_action.intent_type in ('create_event', 'create_task', 'add_reminder', 'mutate_calendar_event'):
        try:
            from apps.core.blueprint.architecture_engine import get_todays_plan
            # Touch today's plan to ensure it's aware of new events
            get_todays_plan(user)
        except ImportError:
            pass  # Architecture engine not installed
        except Exception as e:
            logger.warning("CoS plan refresh failed: %s", e, exc_info=True)

    # ── Step 3: Proactive Insight Engine (PIE) ───────────────────
    # PIE internally triggers PRIE (Step 3) via _trigger_predictions()
    try:
        from django.conf import settings as django_settings

        if not getattr(django_settings, "AI_INSIGHTS_ENABLED", True):
            return

        # Ensure rule modules are registered
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
            "action": enriched_action.intent_type,
            "record_id": record_id,
            "timestamp_utc": get_current_time().isoformat(),
        }

        run_insights(user, event)

    except Exception as e:
        logger.error(f"PIE chain failed for user {user.id}: {e}", exc_info=True)
