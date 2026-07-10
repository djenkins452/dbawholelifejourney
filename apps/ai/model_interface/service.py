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
from apps.ai.model_interface.constitution import (
    ALLOWED_WRITE_INTENTS as _ALLOWED_WRITE_INTENTS,
    CONSTITUTION,
    all_tools,
)
from apps.core.truth import envelope as _env

logger = logging.getLogger(__name__)

# How many prior turns of history to give the model (reuses AssistantMessage — no new
# memory engine). Kept modest to bound tokens.
_HISTORY_LIMIT = 12


def load_conversation_history(conversation, *, limit=_HISTORY_LIMIT):
    """Load prior turns for `conversation` as [{role, content}] for the model, reusing
    the existing AssistantMessage store (Blocker 2 — conversation continuity). Returns
    the most recent `limit` user/assistant text messages, chronologically. Never raises.

    Call this BEFORE persisting the current user message so the current turn is not
    duplicated into the history.
    """
    if conversation is None or not getattr(conversation, "id", None):
        return []
    try:
        from apps.ai.models import AssistantMessage
        rows = list(
            AssistantMessage.objects.filter(
                conversation=conversation, role__in=("user", "assistant"),
                message_type="text",
            ).order_by("-created_at").values("role", "content")[:limit]
        )
    except Exception:  # pragma: no cover - defensive
        logger.warning("mi: history load failed", exc_info=True)
        return []
    rows.reverse()  # chronological
    return [{"role": r["role"], "content": r["content"] or ""}
            for r in rows if (r["content"] or "").strip()]


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

    def _writes_enabled(self) -> bool:
        """Read-only vs write-enabled rollout stage (Blocker 4). Fail-safe to READ-ONLY:
        any error resolves to False, so writes are never accidentally exposed."""
        try:
            return bool(getattr(self.user.preferences, "use_model_interface_writes", False))
        except Exception:
            return False

    # -- standing context: assemble the owned interfaces (assembler owns NOTHING) -----
    def build_standing_context(self, *, page_context=None, writes_enabled=False) -> dict:
        # Four owned interfaces, each at its OWN freshness (Architecture Law — refresh
        # cadence is an ownership boundary). The envelope only ASSEMBLES; it owns none.
        #   AI Relationship          — slow  (projection)
        #   Deterministic Understanding — medium (cache-first; own warm; pending on cold)
        #   Current Context          — fast  (clock, current screen, capabilities)
        from apps.ai.model_interface import understanding
        understanding_read = understanding.read(self.user)
        if isinstance(understanding_read, dict) and understanding_read.get("status") == "pending":
            self._enqueue_understanding_warm()

        ctx = {
            "ai_relationship": get_ai_relationship(self.user),
            "deterministic_understanding": understanding_read,
            "current_context": get_current_context_baseline(
                self.user, page_context=page_context,
            ),
        }
        # Surface OPEN confirmations so the model can resolve a SPECIFIC one on the
        # user's next "yes" (the id lives in a prior tool result, not the transcript).
        if writes_enabled:
            from apps.ai.model_interface import confirmation
            ctx["pending_confirmations"] = confirmation.list_open(self.user)
        return ctx

    def _enqueue_understanding_warm(self):
        """Non-blocking, never-raises warm of the Understanding cache on a cold miss."""
        try:
            from apps.core.celery_utils import safe_enqueue
            from apps.ai.model_interface.tasks import warm_understanding
            safe_enqueue(warm_understanding, self.user.id)
        except Exception:
            logger.debug("mi: understanding warm enqueue skipped", exc_info=True)

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

            # --- Actions: named deterministic intent tools route through the SAME
            #     execute_action → execute_intent → UAIO → bound-confirmation → audit
            #     pipeline. The tool NAME is the intent; args are its real handler params
            #     (Option B — expose the deterministic interface; centralize the pipeline).
            if name in _ALLOWED_WRITE_INTENTS:
                return action_interface.request_action(
                    user, name, args, turn_id=turn_id, surface=surface,
                )
            if name == "resolve_pending_action":
                return action_interface.resolve_pending_action(
                    user, args.get("confirmation_id"),
                    confirm=bool(args.get("confirm", False)),
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
                 request_id="", observer=None, conversation_history=None,
                 writes_enabled=None) -> dict:
        turn_id = request_id or (f"conv-{getattr(conversation, 'id', '')}")
        tools_called = []
        if writes_enabled is None:
            writes_enabled = self._writes_enabled()

        standing_context = self.build_standing_context(
            page_context=page_context, writes_enabled=writes_enabled,
        )
        system_prompt = self._system_prompt(standing_context)
        dispatch = self._make_dispatch(
            turn_id=turn_id, surface=surface, tools_called=tools_called,
            observer=observer,
        )

        answer = self.ai._call_api_with_tools(
            system_prompt, message or "", tools=all_tools(writes_enabled=writes_enabled),
            dispatch=dispatch, user=self.user, endpoint="model_interface",
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
