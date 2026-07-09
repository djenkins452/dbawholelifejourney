# ==============================================================================
# File: apps/ai/model_interface/service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ModelInterfaceService — drives the model over the WLJ four pillars
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
ModelInterfaceService — the runtime that hands WLJ's four pillars to the model.

docs/WLJ_MODEL_INTERFACE_DESIGN.md.

Per turn it:
  1. builds the standing context = CONSTITUTION (fixed) + AI Relationship projection
     (Pillar 3) + Current Context baseline (Pillar 4) + capability index — structured
     DATA, not a prompt of instructions;
  2. exposes the minimal Day-1 tools (3 truth reads + 2 action calls);
  3. drives the model via the existing tool loop; every truth read is wrapped in the
     canonical truth envelope and AUDITED; action calls audit themselves;
  4. records the final response in the audit ledger.

It performs NO reasoning of its own (no classifier, no planner) and issues no direct
writes — all writes go through the action interface → execute_intent → UAIO.
"""

import json
import logging

from apps.ai.cos_services import audit as _audit
from apps.ai.cos_services import (
    action_interface,
    get_ai_relationship,
    get_current_context_baseline,
    get_domain_state,
    get_foundational_health_facts,
    search_history,
)
from apps.ai.model_interface.constitution import CONSTITUTION, all_tools
from apps.core.truth import envelope as _env

logger = logging.getLogger(__name__)


def _wrap_truth(result, source):
    """Wrap an existing cos_services result in the canonical truth envelope, mapping
    the service's own status into an envelope status. Never raises."""
    try:
        status = result.get("status") if isinstance(result, dict) else None
    except Exception:
        status = None

    if status in ("empty",):
        return _env.empty(source=source)
    if status in ("pending",):
        return _env.pending(source=source)
    if status in ("unsupported", "unsupported_domain", "no_state_source"):
        return _env.insufficient_evidence(source=source, reason=str(status))
    if status in ("error",):
        return _env.error(str(result), source=source)
    # ok / plain payload → present it with provenance.
    return _env.make_envelope(result, source=source, status=_env.STATUS_OK)


class ModelInterfaceService:
    def __init__(self, user, ai_service=None):
        self.user = user
        if ai_service is None:
            from apps.ai.services import AIService
            ai_service = AIService()
        self.ai = ai_service

    # -- standing context (structured DATA, not instructions) -----------------
    def build_standing_context(self, *, signals=None, continuity=None) -> dict:
        # Current Context policy (priority / clinical-safety / day-continuity) is
        # CACHE-FIRST (never live-computed on the request path). On a cold miss we
        # fire-and-forget a warm so the next turn is populated, and return pending now.
        if signals is None and continuity is None:
            from apps.ai.model_interface import context_warm
            signals, continuity = context_warm.read(self.user)
            if signals is None and continuity is None:
                self._enqueue_warm()
        return {
            "ai_relationship": get_ai_relationship(self.user),
            "current_context": get_current_context_baseline(
                self.user, signals=signals, continuity=continuity,
            ),
        }

    def _enqueue_warm(self):
        """Non-blocking, never-raises warm of the Current Context cache."""
        try:
            from apps.core.celery_utils import safe_enqueue
            from apps.ai.model_interface.tasks import warm_model_interface_context
            safe_enqueue(warm_model_interface_context, self.user.id)
        except Exception:
            logger.debug("mi: warm enqueue skipped", exc_info=True)

    def _system_prompt(self, standing_context: dict) -> str:
        return (
            CONSTITUTION
            + "\n\n=== STRUCTURED CONTEXT (deterministic; do not invent beyond it) ===\n"
            + json.dumps(standing_context, ensure_ascii=False)
        )

    # -- tool dispatch --------------------------------------------------------
    def _make_dispatch(self, *, turn_id, surface, tools_called, observer=None):
        user = self.user

        def _do(name, args):
            # --- Truth reads: wrap in the envelope + audit (kind='truth') ----
            if name == "get_domain_state":
                raw = get_domain_state(user, args.get("domain", ""))
                out = _wrap_truth(raw, source=f"domain:{args.get('domain', '')}")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    result_digest={"freshness": out.get("freshness"),
                                   "confidence": out.get("confidence")},
                )
                return out
            if name == "search_history":
                raw = search_history(user, args.get("query", ""),
                                     timeframe=args.get("timeframe"))
                out = _wrap_truth(raw, source="history")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    result_digest={"freshness": out.get("freshness")},
                )
                return out
            if name == "get_foundational_health_facts":
                raw = get_foundational_health_facts(user, keys=args.get("keys"))
                out = _wrap_truth(raw, source="health_facts")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    result_digest={"keys": args.get("keys")},
                )
                return out

            # --- Actions: the action interface audits itself (kind='action') -
            if name == "request_action":
                return action_interface.request_action(
                    user, args.get("action", ""), args.get("params") or {},
                    turn_id=turn_id, surface=surface,
                )
            if name == "resolve_pending_action":
                return action_interface.resolve_pending_action(
                    user, confirm=bool(args.get("confirm", False)),
                    turn_id=turn_id, surface=surface,
                )

            return {"status": "error", "error": f"unknown tool '{name}'"}

        def dispatch(name, args):
            args = args if isinstance(args, dict) else {}
            tools_called.append(name)
            result = _do(name, args)
            if observer is not None:  # observability only (validation harness); no-op in prod
                try:
                    observer(name, args, result)
                except Exception:
                    pass
            return result

        return dispatch

    # -- entry point ----------------------------------------------------------
    def generate(self, conversation, message, *, page_context=None, surface="chat",
                 request_id="", signals=None, continuity=None, observer=None,
                 conversation_history=None) -> dict:
        turn_id = request_id or (f"conv-{getattr(conversation, 'id', '')}")
        tools_called = []

        standing_context = self.build_standing_context(
            signals=signals, continuity=continuity,
        )
        system_prompt = self._system_prompt(standing_context)
        dispatch = self._make_dispatch(
            turn_id=turn_id, surface=surface, tools_called=tools_called,
            observer=observer,
        )

        answer = self.ai._call_api_with_tools(
            system_prompt, message or "", tools=all_tools(), dispatch=dispatch,
            user=self.user, endpoint="model_interface",
            conversation_history=conversation_history,
        )
        answer = answer or ""

        _audit.record_tool_call(
            self.user, kind="response", turn_id=turn_id, surface=surface,
            result_status="ok" if answer else "empty",
            result_digest={"answer_len": len(answer),
                           "tools_called": list(tools_called)},
        )
        return {"answer": answer, "tools_called": tools_called,
                "standing_context": standing_context, "turn_id": turn_id}
