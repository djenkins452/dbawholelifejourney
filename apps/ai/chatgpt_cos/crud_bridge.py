# ==============================================================================
# File: apps/ai/chatgpt_cos/crud_bridge.py
# Capability: CRUD-CONFIRMATION COMPLETION for the CoS pipeline (Layer-3 bridge).
#
# The CoS tool loop exposes a single `execute_action` tool whose confirmation is STATELESS:
# a mutation returns status='confirmation_required' and the model is told to "re-call with
# confirmed=true". For a real user replying a bare "Yes", that re-call was unreliable (the
# model had to reconstruct the whole call from memory), so a confirmed mutation could be
# lost — "I wasn't able to move the task." The mutation HANDLER is correct (proven); the gap
# was that the CoS pipeline could INITIATE a confirmation but not COMPLETE it on the next
# turn — that completion existed only in the legacy PersonalAssistant.
#
# This bridge closes the gap by giving the confirmation SERVER-SIDE memory, reusing the
# legacy CRUD flow verbatim:
#   • store  — when `execute_action` returns confirmation_required, remember the pending
#              action (via intent_service.store_pending_crud_action).
#   • resolve— on the next turn, if a pending action exists, hand the reply to
#              intent_service.handle_crud_confirmation, which executes it ONCE (marking it
#              executed before firing), clears it, and returns the real success/failure.
# Deterministic; never raises into the turn.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)


def maybe_resolve_pending_crud(user, message):
    """If a pending CRUD confirmation exists, resolve the user's reply.

    Returns a CoS response dict {answer, tools_called, tools_advertised, lane} when the reply
    is a recognized confirm/cancel (the action executed once, or was cancelled), or None to
    fall through to normal routing (nothing pending, or the reply wasn't a clean yes/no)."""
    try:
        from apps.ai.intent_service import IntentService
        svc = IntentService()
        if not svc.get_pending_crud_action(user):
            return None
        result = svc.handle_crud_confirmation(user, message)
        # None ⇒ unrecognized (re-prompt handled by falling through); 'confirmation_escaped'
        # ⇒ the user changed subject and the pending was cancelled → fall through so the new
        # message is processed normally.
        if result is None or getattr(result, "action_type", None) == "confirmation_escaped":
            return None
        answer = (getattr(result, "message", "") or "").strip() or "Done."
        logger.info(
            "COS_CRUD_CONFIRM user=%s success=%s type=%s",
            getattr(user, "id", None), getattr(result, "success", None),
            getattr(result, "action_type", None))
        return {"answer": answer, "tools_called": [], "tools_advertised": [],
                "lane": "crud_confirmation"}
    except Exception:
        logger.warning("crud_bridge: resolve failed", exc_info=True)
        return None


def maybe_store_pending_crud(user, tool_name, args, result, original_input=""):
    """When a CoS `execute_action` call returns confirmation_required, remember the pending
    action so the NEXT turn's confirmation can complete it deterministically. No-op for any
    other tool or result. Never raises."""
    try:
        if tool_name != "execute_action" or not isinstance(result, dict):
            return
        envelope = result.get("result")
        if not isinstance(envelope, dict) or envelope.get("status") != "confirmation_required":
            return
        action = (args or {}).get("action")
        if not action:
            return
        from apps.ai.intent_service import IntentService
        IntentService().store_pending_crud_action(user, {
            "intent_type": action,
            "parameters": (args or {}).get("params") or {},
            "original_intent": action,
            "original_input": original_input,
            "confirmation_message": envelope.get("message", "Confirm?"),
        })
        logger.info("COS_CRUD_PENDING_STORED user=%s action=%s",
                    getattr(user, "id", None), action)
    except Exception:
        logger.warning("crud_bridge: store failed", exc_info=True)
