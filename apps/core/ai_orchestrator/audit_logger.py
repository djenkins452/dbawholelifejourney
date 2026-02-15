"""
Audit Logger — Record all AI orchestrator interactions.

Every orchestrator invocation is logged for traceability.
Uses Django's structured logging to output JSON-formatted entries.
"""

import logging

from django.utils import timezone

logger = logging.getLogger("apps.ai.orchestrator.audit")


def log_interaction(user, user_input, orchestrator_result):
    """
    Log an orchestrator interaction.

    Args:
        user: Django user instance.
        user_input: Original user message.
        orchestrator_result: OrchestratorResult from the main pipeline.
    """
    try:
        log_data = {
            "user_id": user.id,
            "input_length": len(user_input) if user_input else 0,
            "success": orchestrator_result.success,
            "time_resolved": orchestrator_result.time_resolved,
            "context_resolved": orchestrator_result.context_resolved,
            "needs_clarification": orchestrator_result.needs_clarification,
            "timestamp": timezone.now().isoformat(),
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
