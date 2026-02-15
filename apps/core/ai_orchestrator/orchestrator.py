"""
Unified AI Orchestrator — Central brain for the AI Assistant.

This is the single entry point for all AI-assisted operations.
It coordinates the full pipeline:

    User Input → Context Resolution → Time Resolution → Safety →
    Action Enrichment → Execution → Learning → Audit → Response

IMPORTANT: This does NOT replace the existing PersonalAssistant.send_message().
It enhances the existing pipeline by being called at the right points:

1. BEFORE intent execution: enrich parameters with time/context
2. AFTER intent execution: learn from interaction, audit
"""

import logging

from apps.core.ai_orchestrator.action_router import EnrichedAction, route_action
from apps.core.ai_orchestrator.audit_logger import log_interaction
from apps.core.ai_orchestrator.context_pipeline import resolve_context_pipeline
from apps.core.ai_orchestrator.execution_engine import execute_action
from apps.core.ai_orchestrator.intent_engine import is_time_aware
from apps.core.ai_orchestrator.learning_pipeline import learn_from_interaction
from apps.core.ai_orchestrator.response_builder import build_response
from apps.core.ai_orchestrator.time_pipeline import (
    get_user_timezone,
    resolve_time_pipeline,
)

logger = logging.getLogger(__name__)


class OrchestratorResult:
    """Complete result from the orchestrator pipeline."""

    __slots__ = (
        "success",
        "response",
        "needs_clarification",
        "clarification_question",
        "clarification_source",
        "time_resolved",
        "context_resolved",
        "actions_enriched",
        "action_results",
        "original_input",
        "error",
        "_time_result",
        "_context_result",
    )

    def __init__(self, **kwargs):
        self.success = kwargs.get("success", False)
        self.response = kwargs.get("response")
        self.needs_clarification = kwargs.get("needs_clarification", False)
        self.clarification_question = kwargs.get("clarification_question")
        self.clarification_source = kwargs.get("clarification_source")  # "time" or "context"
        self.time_resolved = kwargs.get("time_resolved", False)
        self.context_resolved = kwargs.get("context_resolved", False)
        self.actions_enriched = kwargs.get("actions_enriched", [])
        self.action_results = kwargs.get("action_results", [])
        self.original_input = kwargs.get("original_input")
        self.error = kwargs.get("error")
        self._time_result = None
        self._context_result = None

    def to_dict(self):
        result = {
            "success": self.success,
            "time_resolved": self.time_resolved,
            "context_resolved": self.context_resolved,
        }
        if self.response:
            result["response"] = self.response
        if self.needs_clarification:
            result["needs_clarification"] = True
            result["clarification_question"] = self.clarification_question
            result["clarification_source"] = self.clarification_source
        if self.actions_enriched:
            result["actions"] = [a.to_dict() for a in self.actions_enriched]
        if self.error:
            result["error"] = self.error
        return result


def process_user_input(user, user_input, page_context=None):
    """
    Main orchestrator entry point.

    Runs the full pipeline: context → time → enrich.
    Does NOT execute actions — that happens when the existing pipeline
    calls enrich_and_execute() with detected intents.

    Args:
        user: Django user instance.
        user_input: Raw user message string.
        page_context: Optional dict with 'url', 'module', 'page_title'.

    Returns:
        OrchestratorResult with resolution results and any clarification needs.
    """
    try:
        # Step 1: Context resolution (SLCME)
        context_result = resolve_context_pipeline(user, user_input, page_context)

        # Step 2: Time resolution (HTIE)
        user_tz = get_user_timezone(user)
        time_result = resolve_time_pipeline(user_input, user_timezone=user_tz)

        # Check if time resolution needs clarification
        if time_result and time_result.is_ambiguous:
            result = OrchestratorResult(
                success=False,
                needs_clarification=True,
                clarification_question=time_result.clarification_question,
                clarification_source="time",
                original_input=user_input,
            )
            log_interaction(user, user_input, result)
            return result

        # Check if context resolution needs confirmation
        if context_result and context_result.needs_confirmation:
            result = OrchestratorResult(
                success=False,
                needs_clarification=True,
                clarification_question=context_result.confirmation_question,
                clarification_source="context",
                original_input=user_input,
            )
            log_interaction(user, user_input, result)
            return result

        # Build result with resolution info
        result = OrchestratorResult(
            success=True,
            time_resolved=bool(
                time_result and time_result.success
            ),
            context_resolved=bool(
                context_result and context_result.resolved
            ),
            original_input=user_input,
        )

        # Store results for use by enrich_and_execute
        result._time_result = time_result
        result._context_result = context_result

        return result

    except Exception as e:
        logger.error(f"Orchestrator error: {e}", exc_info=True)
        return OrchestratorResult(
            success=False,
            original_input=user_input,
            error=str(e),
        )


def enrich_and_execute(user, intent_results, orchestrator_result):
    """
    Enrich detected intents with time/context and execute them.

    Called by the existing PersonalAssistant.send_message() after
    intent recognition, replacing direct calls to execute_intent.

    Args:
        user: Django user instance.
        intent_results: List of IntentResult from existing intent service.
        orchestrator_result: OrchestratorResult from process_user_input().

    Returns:
        List of ActionResult from execution.
    """
    from apps.ai.intent_service import intent_service

    time_result = getattr(orchestrator_result, "_time_result", None)
    context_result = getattr(orchestrator_result, "_context_result", None)
    action_results = []
    enriched_actions = []

    for intent_result in intent_results:
        # Route and enrich
        enriched = route_action(
            intent_type=intent_result.intent_type,
            parameters=intent_result.parameters,
            time_result=time_result,
            context_result=context_result,
            original_input=orchestrator_result.original_input,
        )
        enriched_actions.append(enriched)

        # Execute through existing handler
        result = execute_action(user, enriched)
        action_results.append(result)

        # Learn from successful execution + run insights
        if result and result.success:
            learn_from_interaction(
                user=user,
                user_input=orchestrator_result.original_input,
                action_result=result,
                enriched_action=enriched,
            )

            # Fire PIE event for proactive insights
            _fire_insight_event(user, enriched, result)

    # Update orchestrator result
    orchestrator_result.actions_enriched = enriched_actions
    orchestrator_result.action_results = action_results

    # Build enhanced response
    orchestrator_result.response = build_response(orchestrator_result)

    # Audit log
    log_interaction(user, orchestrator_result.original_input, orchestrator_result)

    return action_results


def _fire_insight_event(user, enriched_action, action_result):
    """
    Fire a PIE event after a successful action.

    Wrapped in try/except so insight failures never break the main flow.
    """
    try:
        from django.conf import settings as django_settings

        if not getattr(django_settings, "AI_INSIGHTS_ENABLED", True):
            return

        # Import rule modules to ensure they're registered
        import apps.core.ai_insights.rules_health  # noqa: F401
        import apps.core.ai_insights.rules_body_composition  # noqa: F401
        import apps.core.ai_insights.rules_goals  # noqa: F401
        import apps.core.ai_insights.rules_habits  # noqa: F401
        import apps.core.ai_insights.rules_journal  # noqa: F401

        from django.utils import timezone as tz
        from apps.core.ai_insights.insight_engine import run_insights

        event = {
            "event_type": "record_created",
            "module": enriched_action.module,
            "action": enriched_action.intent_type,
            "record_id": (
                action_result.created_object.get("id")
                if action_result.created_object
                else None
            ),
            "timestamp_utc": tz.now().isoformat(),
        }

        run_insights(user, event)

    except Exception as e:
        logger.error(f"PIE event fire error: {e}", exc_info=True)
