"""
Response Builder — Build human-friendly responses from orchestrator results.

Enhances action result messages with temporal context when HTIE
resolved a time expression.
"""

import logging

logger = logging.getLogger(__name__)


def build_response(orchestrator_result):
    """
    Build the final user-facing response string.

    Enhances action messages with resolved time context.

    Args:
        orchestrator_result: OrchestratorResult from the orchestrator.

    Returns:
        String response for the user.
    """
    # If clarification needed, return the question
    if orchestrator_result.needs_clarification:
        return orchestrator_result.clarification_question

    # If no actions were taken, return empty (existing pipeline handles chat)
    if not orchestrator_result.action_results:
        return None

    parts = []
    for i, result in enumerate(orchestrator_result.action_results):
        message = result.message

        # Enhance with time context if available
        if orchestrator_result.actions_enriched and i < len(
            orchestrator_result.actions_enriched
        ):
            action = orchestrator_result.actions_enriched[i]
            time_expr = action.parameters.get("_time_expression")
            recorded_at = action.parameters.get("recorded_at")

            if time_expr and recorded_at and result.success:
                # Add temporal context to the response
                formatted_date = recorded_at.strftime("%B %d, %Y")
                formatted_time = recorded_at.strftime("%I:%M %p").lstrip("0")

                # Only add date context if it differs from "now"
                if time_expr:
                    message = f"{message} (for {formatted_date})"

        parts.append(message)

    return " ".join(parts)
