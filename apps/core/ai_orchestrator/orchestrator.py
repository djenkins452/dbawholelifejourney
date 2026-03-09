"""
Unified AI Orchestrator — Central brain for the AI Assistant.

This is the single entry point for all AI-assisted operations.
It coordinates the full pipeline:

    User Input → Context Resolution → Time Resolution → Semantic Understanding →
    Safety → Action Enrichment → Execution → Learning → Audit → Response

IMPORTANT: This does NOT replace the existing PersonalAssistant.send_message().
It enhances the existing pipeline by being called at the right points:

1. BEFORE intent execution: enrich parameters with time/context/semantics
2. AFTER intent execution: learn from interaction, audit
"""

import logging

from apps.core.ai_orchestrator.action_router import EnrichedAction, route_action
from apps.core.ai_orchestrator.audit_logger import log_interaction
from apps.core.ai_orchestrator.context_pipeline import resolve_context_pipeline
from apps.core.ai_orchestrator.execution_engine import execute_action
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
        "_semantic_result",
    )

    def __init__(self, **kwargs):
        self.success = kwargs.get("success", False)
        self.response = kwargs.get("response")
        self.needs_clarification = kwargs.get("needs_clarification", False)
        self.clarification_question = kwargs.get("clarification_question")
        self.clarification_source = kwargs.get("clarification_source")  # "time", "context", or "semantic"
        self.time_resolved = kwargs.get("time_resolved", False)
        self.context_resolved = kwargs.get("context_resolved", False)
        self.actions_enriched = kwargs.get("actions_enriched", [])
        self.action_results = kwargs.get("action_results", [])
        self.original_input = kwargs.get("original_input")
        self.error = kwargs.get("error")
        self._time_result = None
        self._context_result = None
        self._semantic_result = None

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

        # Step 3: Semantic understanding (SUE)
        semantic_result = _run_semantic_understanding(user, user_input, page_context)

        # Check if SUE detected ambiguity that needs clarification
        if semantic_result and semantic_result.is_ambiguous:
            # Only halt for ambiguity if confidence is too low to proceed
            if not semantic_result.confidence.is_safe_to_execute:
                result = OrchestratorResult(
                    success=False,
                    needs_clarification=True,
                    clarification_question=semantic_result.clarification_question,
                    clarification_source="semantic",
                    original_input=user_input,
                )
                result._semantic_result = semantic_result
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
        result._semantic_result = semantic_result

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

    learning_mode_blocked = False
    LEARNING_MODE_CONTROL_INTENTS = {'enter_learning_mode', 'exit_learning_mode'}

    for intent_result in intent_results:
        # If Learning Mode blocked a domain action, skip remaining domain
        # actions — but always allow control-plane intents through.
        if learning_mode_blocked:
            if intent_result.intent_type not in LEARNING_MODE_CONTROL_INTENTS:
                continue

        # Route and enrich
        enriched = route_action(
            intent_type=intent_result.intent_type,
            parameters=intent_result.parameters,
            time_result=time_result,
            context_result=context_result,
            original_input=orchestrator_result.original_input,
        )
        enriched_actions.append(enriched)

        # ── Layer 1: Activity Reconciliation ─────────────────────
        # Checks for existing activities matching the create/log intent.
        # All decisions are proposals — nothing executes without CRUD gate.
        recon_result = None
        try:
            from apps.core.ai_orchestrator.activity_reconciliation import (
                reconcile_activity,
                ReconciliationDecision,
            )
            recon_result = reconcile_activity(user, enriched)

            if recon_result.decision == ReconciliationDecision.RESCHEDULE:
                # Rewrite enriched action to the mutate equivalent
                enriched = EnrichedAction(
                    intent_type=recon_result.redirected_intent,
                    parameters=recon_result.redirected_params,
                    original_input=enriched.original_input,
                )
                enriched_actions[-1] = enriched
            # CREATE, SKIP, CONFIRM all fall through to CRUD gate
        except ImportError:
            pass  # Module not installed yet
        except Exception as e:
            logger.error(
                "Activity reconciliation failed (user=%s): %s",
                user.id, e, exc_info=True,
            )

        # ── Layer 2: CRUD Confirmation Gate ──────────────────────
        # All write operations require explicit user confirmation.
        # Read-only / control-plane intents pass through to execution.
        try:
            from apps.core.ai_orchestrator.crud_confirmation import (
                requires_confirmation,
                build_crud_confirmation_message,
            )
            if requires_confirmation(enriched.intent_type):
                from apps.ai.intent_service import ActionResult
                from django.utils import timezone as dj_tz

                msg = build_crud_confirmation_message(enriched, recon_result)
                intent_service.store_pending_crud_action(user, {
                    'intent_type': enriched.intent_type,
                    'parameters': enriched.parameters,
                    'original_intent': intent_result.intent_type,
                    'original_input': orchestrator_result.original_input,
                    'recon_decision': (
                        recon_result.decision.value if recon_result else 'none'
                    ),
                    'recon_context': (
                        recon_result.matched_object if recon_result else None
                    ),
                    'confirmation_message': msg,
                })
                logger.info(
                    "[CRUD_GATE] Pending: %s user=%s recon=%s",
                    enriched.intent_type, user.id,
                    recon_result.decision.value if recon_result else 'none',
                )
                result = ActionResult(
                    success=False,
                    message=msg,
                    error='crud_confirmation_required',
                    action_type=enriched.intent_type,
                )
                action_results.append(result)
                continue  # Skip execution — wait for user confirmation
        except ImportError:
            pass  # Module not installed yet
        except Exception as e:
            # FAILSAFE: CRUD gate failure blocks execution (fail-closed)
            logger.error(
                "CRUD gate failed (blocking execution, user=%s): %s",
                user.id, e, exc_info=True,
            )
            from apps.ai.intent_service import ActionResult
            result = ActionResult(
                success=False,
                message="I wasn't able to process that safely. Please try again.",
                error='crud_gate_error',
                action_type=enriched.intent_type,
            )
            action_results.append(result)
            continue

        # ── Execute (only reached for PASSTHROUGH_INTENTS) ───────
        result = execute_action(user, enriched)
        action_results.append(result)

        # Short-circuit on Learning Mode — one message is enough
        if result and getattr(result, 'error', None) == 'learning_mode_active':
            learning_mode_blocked = True
            continue

        # Learn from successful execution
        # Note: Intelligence chain (SAE → PIE → PRIE) is now centralized
        # in execute_action() and fires automatically on success.
        if result and result.success:
            try:
                learn_from_interaction(
                    user=user,
                    user_input=orchestrator_result.original_input,
                    action_result=result,
                    enriched_action=enriched,
                )
            except Exception as e:
                logger.error(
                    "learn_from_interaction failed for %s: %s",
                    enriched.intent_type, e, exc_info=True,
                )

    # Update orchestrator result
    orchestrator_result.actions_enriched = enriched_actions
    orchestrator_result.action_results = action_results

    # Build enhanced response
    try:
        orchestrator_result.response = build_response(orchestrator_result)
    except Exception as e:
        logger.error("build_response failed: %s", e, exc_info=True)
        # Fallback: assemble from individual action messages
        parts = [r.message for r in action_results if r and r.message]
        orchestrator_result.response = " ".join(parts) if parts else None

    # Audit log
    try:
        log_interaction(user, orchestrator_result.original_input, orchestrator_result)
    except Exception as e:
        logger.error("log_interaction failed: %s", e, exc_info=True)

    return action_results


def _run_semantic_understanding(user, user_input, page_context):
    """
    Run SUE semantic understanding with ImportError guard.

    SUE failures must never break the orchestrator pipeline.
    Returns SemanticResult or None.
    """
    try:
        from apps.core.ai_semantics.semantic_engine import interpret

        return interpret(user, user_input, context=page_context)
    except ImportError:
        logger.debug("SUE not installed, skipping semantic understanding")
        return None
    except Exception as e:
        logger.error(f"SUE failed: {e}", exc_info=True)
        return None
