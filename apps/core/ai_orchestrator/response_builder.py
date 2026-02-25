"""
Response Builder — Build human-friendly responses from orchestrator results.

Enhances action result messages with temporal context when HTIE
resolved a time expression, and attaches URL navigation metadata
via the ActionContract system (Phase 7).
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

    # Deduplicate suppression messages — if all results share the same
    # error type (e.g. learning_mode_active), return one clean message.
    error_types = {
        getattr(r, 'error', None)
        for r in orchestrator_result.action_results
        if getattr(r, 'error', None)
    }
    if len(error_types) == 1 and len(orchestrator_result.action_results) >= 1:
        first_error = orchestrator_result.action_results[0]
        if not any(r.success for r in orchestrator_result.action_results):
            return first_error.message

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


def build_response_with_contracts(orchestrator_result):
    """
    Build response string AND action contracts with URL metadata.

    Returns both the text response and structured action contract data
    for the frontend to render navigation links and action buttons.

    Args:
        orchestrator_result: OrchestratorResult from the orchestrator.

    Returns:
        Tuple of (response_string, action_contracts_list).
        action_contracts_list is a list of dicts or empty list.
    """
    response = build_response(orchestrator_result)

    # Build action contracts for successful actions
    contracts = []
    if orchestrator_result.action_results:
        try:
            from apps.core.ai_orchestrator.action_contracts import (
                enrich_response_with_contracts,
            )
            contracts = enrich_response_with_contracts(
                orchestrator_result.action_results,
                orchestrator_result.actions_enriched,
            )
        except Exception as e:
            logger.debug("Action contract generation skipped: %s", e)

    return response, contracts
