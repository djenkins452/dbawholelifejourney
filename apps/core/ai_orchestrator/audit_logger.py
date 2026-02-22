"""
Audit Logger — Record all AI orchestrator interactions.

Every orchestrator invocation is logged for traceability.
Uses Django's structured logging to output JSON-formatted entries.
"""

import logging

from apps.core.time.system_clock import get_current_time

logger = logging.getLogger("apps.ai.orchestrator.audit")


def log_interaction(user, user_input, orchestrator_result):
    """
    Log an orchestrator interaction.

    During Learning Mode, action-specific audit entries are suppressed.
    System integrity entries (conversation, governance, safety) are preserved.

    Args:
        user: Django user instance.
        user_input: Original user message.
        orchestrator_result: OrchestratorResult from the main pipeline.
    """
    # During Learning Mode, suppress audit entries for action execution attempts
    try:
        from apps.core.blueprint.learning_mode import is_learning_mode_active
        if is_learning_mode_active(user) and orchestrator_result.actions_enriched:
            logger.debug(
                "Audit log suppressed (Learning Mode): user=%s actions=%s",
                user.id,
                [a.intent_type for a in orchestrator_result.actions_enriched],
            )
            return
    except Exception:
        pass  # Audit suppression check must never break logging

    try:
        log_data = {
            "user_id": user.id,
            "input_length": len(user_input) if user_input else 0,
            "success": orchestrator_result.success,
            "time_resolved": orchestrator_result.time_resolved,
            "context_resolved": orchestrator_result.context_resolved,
            "needs_clarification": orchestrator_result.needs_clarification,
            "timestamp": get_current_time().isoformat(),
        }

        if orchestrator_result.actions_enriched:
            log_data["actions"] = [
                a.intent_type for a in orchestrator_result.actions_enriched
            ]

        if orchestrator_result.needs_clarification:
            log_data["clarification_question"] = (
                orchestrator_result.clarification_question
            )

        logger.info(
            f"AI Orchestrator: user={user.id} success={orchestrator_result.success}",
            extra=log_data,
        )

    except Exception as e:
        # Audit logging must never break the main flow
        logger.error(f"Audit log error: {e}", exc_info=True)
