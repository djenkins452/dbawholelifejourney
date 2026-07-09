# ==============================================================================
# File: apps/ai/cos_services/action_interface.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Action interface (Pillar 2) — STATEFUL server-side confirmation
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Action interface — Pillar 2 of the WLJ ↔ model interface.

docs/WLJ_MODEL_INTERFACE_DESIGN.md §Pillar 2 / §4.

The model REQUESTS an action; WLJ executes it safely and reports the REAL result. This
layer adds the one thing the CoS action path was missing: **stateful, server-side
confirmation.**

Eliminate-the-class fix: the previous CoS confirmation was *stateless* — it told the
model to "re-call with confirmed=true," and a bare user "yes" never reliably produced
that confirmed re-call ("confirmed but nothing happened"). Here, when an action needs
confirmation WLJ **stores the pending action server-side** (reusing the existing
`store_pending_confirmation` cache) and a later `resolve_pending_action(confirm=True)`
executes the STORED action. The model never has to reconstruct the confirmed call.

Guarantees:
* NO direct model writes — everything goes through `execute_action` → `execute_intent`
  → UAIO (the single existing write path). Safety gates unchanged.
* Result is narrated from the ACTUAL `ActionResult.message` — never an assumed outcome.
* Every request/resolution is audited (kind='action').
* Never raises.
"""

import logging

from apps.ai.cos_services.action_execution import execute_action
from apps.ai.cos_services.audit import record_tool_call

logger = logging.getLogger(__name__)

# Interface envelope statuses (distinct from execute_action's internal statuses).
OK = "ok"
CONFIRMATION_REQUIRED = "confirmation_required"
DECLINED = "declined"
ERROR = "error"


def _map_result(env: dict) -> dict:
    """Map an execute_action envelope to the interface result envelope."""
    status = env.get("status")
    message = env.get("message", "") or ""
    if status == "success":
        return {"status": OK, "result": message}
    if status == "confirmation_required":
        return {"status": CONFIRMATION_REQUIRED, "result": message}
    # failed / denied / error → error, but carry the REAL reason.
    return {
        "status": ERROR,
        "result": message or "That action could not be completed.",
        "code": env.get("code", status),
    }


def _intent_service():
    from apps.ai.intent_service import IntentService
    return IntentService()


def _store_pending(user, action, params):
    """Persist the pending action server-side (so 'yes' resolves the STORED action)."""
    from apps.ai.intent_service import IntentResult
    svc = _intent_service()
    clean = {k: v for k, v in (params or {}).items() if k != "confirmed"}
    svc.store_pending_confirmation(
        user, IntentResult(intent_type=action, parameters=clean, confidence=1.0)
    )


def request_action(user, action, params=None, *, turn_id="", surface="") -> dict:
    """Request one action. If it needs confirmation, WLJ stores it server-side and
    returns `confirmation_required`; otherwise it executes and returns the real result.
    """
    params = dict(params) if isinstance(params, dict) else {}
    try:
        env = execute_action(user, action, params)
        out = _map_result(env)
        if out["status"] == CONFIRMATION_REQUIRED:
            _store_pending(user, action, params)
            out["confirmation"] = {"pending": True}
    except Exception:  # never break a turn
        logger.warning("action_interface.request_action failed action=%s user=%s",
                       action, getattr(user, "id", "?"), exc_info=True)
        out = {"status": ERROR, "result": "That action could not be completed.",
               "code": "interface_error"}

    record_tool_call(
        user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
        args={k: v for k, v in params.items() if k != "confirmed"},
        result_status=out["status"], result_digest={"result": out.get("result", "")},
    )
    return out


def resolve_pending_action(user, *, confirm=True, turn_id="", surface="") -> dict:
    """Resolve a previously-requested action awaiting confirmation.

    confirm=True  → execute the STORED action (with confirmed=true) and clear it.
    confirm=False → cancel it and clear it (declined). The model does not reconstruct
    the action — WLJ held it.
    """
    svc = _intent_service()
    try:
        pending = svc.get_pending_confirmation(user)
    except Exception:  # pragma: no cover - defensive
        pending = None

    if not pending:
        out = {"status": ERROR, "result": "There's nothing awaiting confirmation.",
               "code": "nothing_pending"}
        record_tool_call(user, kind="action", tool_name="", turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         result_digest={"code": "nothing_pending"})
        return out

    action = pending.get("intent_type", "")
    params = dict(pending.get("parameters", {}) or {})

    if not confirm:
        svc.clear_pending_confirmation(user)
        out = {"status": DECLINED, "result": "Okay — I won't do that."}
        record_tool_call(user, kind="action", tool_name=action, turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         result_digest={"declined": True})
        return out

    # Execute the STORED action, authorized.
    params["confirmed"] = True
    try:
        env = execute_action(user, action, params)
        out = _map_result(env)
    except Exception:  # never break a turn
        logger.warning("action_interface.resolve failed action=%s user=%s",
                       action, getattr(user, "id", "?"), exc_info=True)
        out = {"status": ERROR, "result": "That action could not be completed.",
               "code": "interface_error"}
    finally:
        svc.clear_pending_confirmation(user)

    record_tool_call(
        user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
        args={k: v for k, v in params.items() if k != "confirmed"},
        result_status=out["status"], result_digest={"result": out.get("result", "")},
    )
    return out
