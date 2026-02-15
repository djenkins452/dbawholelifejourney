"""
Action Router — Maps orchestrator results to the existing ActionHandler.

Does NOT replace the existing intent_service.execute_intent().
Provides pre-execution enrichment (time, context) and post-execution
hooks (learning, audit).
"""

import logging

from apps.core.ai_orchestrator.intent_engine import (
    get_intent_module,
    is_context_aware,
    is_time_aware,
)
from apps.core.ai_orchestrator.time_pipeline import enrich_parameters_with_time

logger = logging.getLogger(__name__)


class EnrichedAction:
    """An action ready for execution with enriched parameters."""

    __slots__ = (
        "intent_type",
        "parameters",
        "module",
        "time_resolved",
        "context_resolved",
        "original_input",
    )

    def __init__(self, intent_type, parameters, original_input=None):
        self.intent_type = intent_type
        self.parameters = parameters
        self.module = get_intent_module(intent_type)
        self.time_resolved = parameters.get("_time_resolved", False)
        self.context_resolved = parameters.get("_context_resolved", False)
        self.original_input = original_input

    def to_dict(self):
        return {
            "intent_type": self.intent_type,
            "module": self.module,
            "time_resolved": self.time_resolved,
            "context_resolved": self.context_resolved,
            "parameters": {
                k: v
                for k, v in self.parameters.items()
                if not k.startswith("_")
            },
        }


def route_action(intent_type, parameters, time_result=None, context_result=None,
                  original_input=None):
    """
    Enrich intent parameters with time/context resolution and prepare for execution.

    This is called BETWEEN intent recognition and intent execution.

    Args:
        intent_type: The detected intent (e.g., 'log_weight').
        parameters: Dict of extracted parameters.
        time_result: InterpretationResult from HTIE (optional).
        context_result: MemoryResolution from SLCME (optional).
        original_input: The original user message.

    Returns:
        EnrichedAction ready for execution.
    """
    enriched_params = dict(parameters)

    # Enrich with resolved time if applicable
    if time_result and is_time_aware(intent_type):
        enrich_parameters_with_time(enriched_params, time_result)

    # Enrich with resolved context if applicable
    if context_result and context_result.resolved and is_context_aware(intent_type):
        enriched_params["_context_type"] = context_result.meaning_type
        enriched_params["_context_id"] = context_result.meaning_identifier
        enriched_params["_context_resolved"] = True

    return EnrichedAction(
        intent_type=intent_type,
        parameters=enriched_params,
        original_input=original_input,
    )
