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

The model REQUESTS an action; WLJ executes it safely and reports the REAL result.
Confirmation is a **bound transaction** (Blocker 1 hardening): each confirmation has its
own identity, and `resolve_pending_action(confirmation_id, confirm)` executes a SPECIFIC
confirmation by id — never "whatever happens to be stored." A second request cannot be
silently confirmed by a bare "yes"; a wrong/expired id fails honestly. See
`apps/ai/model_interface/confirmation.py`.

Guarantees:
* NO direct model writes — everything goes through `execute_action` → `execute_intent`
  → UAIO (the single existing write path). Safety gates unchanged.
* Result is narrated from the ACTUAL `ActionResult.message` — never an assumed outcome.
* Confirmation is resolved by explicit `confirmation_id` (single-use, per-user, expiring).
* Every request/resolution is audited (kind='action').
* Never raises.
"""

import logging

from apps.ai.cos_services.action_execution import execute_action
from apps.ai.cos_services.audit import record_tool_call
from apps.ai.model_interface import confirmation as _confirm

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


def request_action(user, action, params=None, *, turn_id="", surface="") -> dict:
    """Request one action. If it needs confirmation, WLJ mints a BOUND confirmation and
    returns `confirmation_required` with its `confirmation_id` + summary; otherwise it
    executes and returns the real result.
    """
    params = dict(params) if isinstance(params, dict) else {}
    try:
        env = execute_action(user, action, params)
        out = _map_result(env)
        if out["status"] == CONFIRMATION_REQUIRED:
            summary = _confirm.summarize(action, params)
            handle = _confirm.create(user, action, params, summary)
            if handle:
                out["result"] = f"Please confirm: {summary}"
                out["confirmation"] = handle          # {confirmation_id, summary, expires_in}
            else:
                out = {"status": ERROR, "code": "confirmation_store_failed",
                       "result": "I couldn't set up the confirmation. Please try again."}
    except Exception:  # never break a turn
        logger.warning("action_interface.request_action failed action=%s user=%s",
                       action, getattr(user, "id", "?"), exc_info=True)
        out = {"status": ERROR, "result": "That action could not be completed.",
               "code": "interface_error"}

    record_tool_call(
        user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
        args={k: v for k, v in params.items() if k != "confirmed"},
        result_status=out["status"],
        result_digest={"result": out.get("result", ""),
                       "confirmation_id": (out.get("confirmation") or {}).get("confirmation_id")},
    )
    return out


def resolve_pending_action(user, confirmation_id=None, *, confirm=True,
                           turn_id="", surface="") -> dict:
    """Resolve a SPECIFIC bound confirmation by id.

    confirm=True  → execute exactly that confirmation's action (confirmed=true), consume it.
    confirm=False → cancel exactly that confirmation, consume it (declined).
    A missing/expired/wrong id fails honestly — WLJ never executes "whatever is stored."
    """
    rec = _confirm.get(user, confirmation_id)
    if not rec:
        out = {"status": ERROR, "code": "no_matching_confirmation",
               "result": ("I don't have a pending action with that confirmation to act "
                          "on — it may have expired. Ask me again and I'll re-confirm.")}
        record_tool_call(user, kind="action", tool_name="", turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         result_digest={"confirmation_id": confirmation_id,
                                        "code": "no_matching_confirmation"})
        return out

    action = rec.get("action", "")
    params = dict(rec.get("params", {}) or {})

    if not confirm:
        _confirm.consume(user, confirmation_id)
        out = {"status": DECLINED, "result": "Okay — I won't do that."}
        record_tool_call(user, kind="action", tool_name=action, turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         result_digest={"confirmation_id": confirmation_id,
                                        "declined": True})
        return out

    # Execute exactly this confirmation's action, authorized.
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
        _confirm.consume(user, confirmation_id)  # single-use, always

    record_tool_call(
        user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
        args={k: v for k, v in params.items() if k != "confirmed"},
        result_status=out["status"],
        result_digest={"confirmation_id": confirmation_id,
                       "result": out.get("result", "")},
    )
    return out
