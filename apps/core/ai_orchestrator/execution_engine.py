"""
Execution Engine — Delegates to existing ActionHandler after enrichment.

This wraps the existing IntentService.execute_intent() with pre/post hooks
for the orchestrator pipeline.
"""

import logging

from apps.core.ai_orchestrator.safety_engine import validate_action

logger = logging.getLogger(__name__)


def execute_action(user, enriched_action):
    """
    Execute an enriched action through the existing ActionHandler.

    Pipeline:
    1. Safety validation
    2. Delegate to existing execute_intent
    3. Return result for learning/audit pipeline

    Args:
        user: Django user instance.
        enriched_action: EnrichedAction from action_router.

    Returns:
        ActionResult from the existing intent service, or None on safety failure.
    """
    from apps.ai.intent_service import IntentResult, intent_service

    # Step 1: Safety check
    safety_result = validate_action(enriched_action)
    if not safety_result.is_safe:
        logger.warning(
            f"Action blocked by safety engine: {enriched_action.intent_type} - "
            f"{safety_result.reason}"
        )
        from apps.ai.intent_service import ActionResult

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
        return result
    except Exception as e:
        logger.error(
            f"Execution error for {enriched_action.intent_type}: {e}",
            exc_info=True,
        )
        from apps.ai.intent_service import ActionResult

        return ActionResult(
            success=False,
            message="Sorry, I couldn't complete that action.",
            error=str(e),
            action_type=enriched_action.intent_type,
        )
