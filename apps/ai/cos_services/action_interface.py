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
    out = {
        "status": ERROR,
        "result": message or "That action could not be completed.",
        "code": env.get("code", status),
    }
    evidence = env.get("evidence")
    if isinstance(evidence, dict) and evidence:
        # GROUNDING CONTRACT: `establishes_absence` tells the model whether this failure
        # actually proves the object is absent from WLJ, or only that this handler/type
        # did not match. A type-scoped miss must never be reported as global absence.
        out["evidence"] = evidence
    return out


def request_confirmation_for(user, action, params=None, *, turn_id="", surface="",
                             conversation_id=None):
    """Mint a BOUND confirmation for a write that must not execute yet, and MUTATE NOTHING.

    For model-facing writes that do not run through `request_action` (currently
    `complete_execution_item`). Reuses the SAME confirmation store, binding and client
    view — there is no second confirmation system. Returns the interface result, or None
    if a confirmation could not be minted (caller then fails closed).

    The confirmation carries the EXACT target params, so the later "yes" executes that
    bound action and never re-resolves from a name or the current action.
    """
    params = dict(params) if isinstance(params, dict) else {}
    try:
        summary = _confirm.summarize(action, params)
        handle = _confirm.create(user, action, params, summary,
                                 conversation_id=conversation_id)
        if not handle:
            return None
        rec = _confirm.get(user, handle["confirmation_id"])
        out = {
            "status": CONFIRMATION_REQUIRED,
            "result": f"Please confirm: {summary}",
            "confirmation": (_confirm.client_view(rec) if rec else handle),
        }
        record_tool_call(
            user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
            args=params, result_status=CONFIRMATION_REQUIRED,
            conversation_id=conversation_id,
            result_digest={"status": CONFIRMATION_REQUIRED,
                           "confirmation_id": handle.get("confirmation_id"),
                           "mutated": False},
        )
        return out
    except Exception:
        logger.warning("action_interface.request_confirmation_for failed action=%s user=%s",
                       action, getattr(user, "id", "?"), exc_info=True)
        return None


def request_action(user, action, params=None, *, turn_id="", surface="",
                   conversation_id=None) -> dict:
    """Request one action. If it needs confirmation, WLJ mints a BOUND, CONVERSATION-BOUND
    confirmation carrying its presentation-independent Rich Confirmation `view`, and returns
    `confirmation_required` with the client-ready confirmation payload; otherwise it executes
    and returns the real result.
    """
    params = dict(params) if isinstance(params, dict) else {}
    try:
        env = execute_action(user, action, params)
        out = _map_result(env)
        # Object-Level Reveal: carry the created/updated object descriptor (model/id/url) so
        # the caller can reveal the SPECIFIC object, not just its workspace. (env["result"] is
        # the handler's created_object; _map_result intentionally maps "result" to the message.)
        if out["status"] == OK and isinstance(env.get("result"), dict):
            out["created_object"] = env["result"]
        if out["status"] == CONFIRMATION_REQUIRED:
            summary = _confirm.summarize(action, params)
            # Build the presentation-independent view (title/summary/preview/actions) from
            # the handler's structured confirmation_detail — the ONE source both the on-screen
            # card and the typed pre-parser read.
            try:
                from apps.ai.confirmation_contract import build_view
                view = build_view(action, params, env.get("confirmation_detail"))
            except Exception:  # pragma: no cover - never block a confirmation
                logger.warning("action_interface: build_view failed action=%s", action,
                               exc_info=True)
                view = None
            handle = _confirm.create(
                user, action, params, summary, view=view,
                conversation_id=conversation_id,
                source_artifact_id=params.get("source_artifact_id"),
            )
            if handle:
                rec = _confirm.get(user, handle["confirmation_id"])
                client = _confirm.client_view(rec) if rec else None
                out["result"] = (env.get("message") or f"Please confirm: {summary}")
                out["confirmation"] = client or handle   # rich client payload
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
        conversation_id=conversation_id,
        result_digest={"result": out.get("result", ""),
                       "confirmation_id": (out.get("confirmation") or {}).get("confirmation_id")},
    )
    return out


def resolve_pending_action(user, confirmation_id=None, *, confirm=True, choice=None,
                           turn_id="", surface="", conversation_id=None) -> dict:
    """Resolve a SPECIFIC bound confirmation by id — the ONE resolver for BOTH a clicked
    button and a typed confirm/cancel.

    choice        → the selected action key (e.g. 'confirm'/'cancel'/'merge'/'keep_both').
                    'cancel' (or confirm=False) declines. Any other key executes that
                    action; for a binary confirmation the primary key is 'confirm'.
    A missing id → `no_matching_confirmation`; a resolved/cancelled one → `already_resolved`
    (never re-executes). WLJ never executes "whatever is stored."
    """
    rec = _confirm.get(user, confirmation_id)
    if not rec:
        # Distinguish an already-resolved replay from a truly-gone (expired) confirmation.
        tomb = _confirm.peek(user, confirmation_id)
        if tomb is not None and tomb.get("status") in ("resolved", "cancelled"):
            code, msg = "already_resolved", "That confirmation was already handled."
        else:
            code, msg = ("no_matching_confirmation",
                         "I don't have a pending action with that confirmation to act on — "
                         "it may have expired. Ask me again and I'll re-confirm.")
        out = {"status": ERROR, "code": code, "result": msg,
               "confirmation_id": confirmation_id}
        record_tool_call(user, kind="action", tool_name="", turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         conversation_id=conversation_id,
                         result_digest={"confirmation_id": confirmation_id, "code": code})
        return out

    # Resolve the chosen key: default primary is 'confirm'; 'cancel' always declines.
    key = (choice or ("confirm" if confirm else "cancel"))
    is_cancel = (key == "cancel") or (confirm is False and not choice)

    action = rec.get("action", "")
    params = dict(rec.get("params", {}) or {})
    # N-way: an explicit action option may carry its own action/params (Medication Merge, …).
    chosen = _find_option(rec, key) if (key not in ("confirm", "cancel")) else None
    if chosen:
        action = chosen.get("action") or action
        if isinstance(chosen.get("params"), dict):
            params.update(chosen["params"])
        else:
            params["choice"] = key

    if is_cancel:
        _confirm.consume(user, confirmation_id, status="cancelled", choice="cancel")
        out = {"status": DECLINED, "result": "Okay — I won't do that.",
               "confirmation_id": confirmation_id}
        record_tool_call(user, kind="action", tool_name=action, turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         conversation_id=conversation_id,
                         result_digest={"confirmation_id": confirmation_id, "declined": True})
        return out

    # Execute exactly this confirmation's action, authorized.
    params["confirmed"] = True
    # `complete_execution_item` is a model-interface tool, not a DAY1 intent, so it is not
    # dispatchable by `execute_action`. Route the CONFIRMED action back to the completion
    # service with the EXACT bound params — the target is never re-resolved from a name or
    # from whatever the current action happens to be by now.
    if action == "complete_execution_item":
        try:
            from apps.ai.cos_services.execution_completion import (
                complete_execution_item as _cei,
            )
            done = _cei(user, kind=params.get("kind"), title=params.get("title"),
                        day=params.get("day"), content=params.get("content"),
                        source_type=params.get("source_type"),
                        source_id=params.get("source_id"),
                        undo=bool(params.get("undo")))
            _confirm.consume(user, confirmation_id, status="resolved",
                             choice="confirm")   # single-use, same as below
            ok = done.get("status") in ("recorded", "already_complete", "reversed")
            return {"status": OK if ok else ERROR,
                    "result": done.get("message") or done.get("status"),
                    "code": None if ok else done.get("status"),
                    "evidence": done.get("detail") or {}}
        except Exception:
            logger.warning("action_interface: bound completion failed user=%s",
                           getattr(user, "id", "?"), exc_info=True)
            return {"status": ERROR, "code": "interface_error",
                    "result": "That confirmed action could not be completed."}
    try:
        env = execute_action(user, action, params)
        out = _map_result(env)
    except Exception:  # never break a turn
        logger.warning("action_interface.resolve failed action=%s user=%s",
                       action, getattr(user, "id", "?"), exc_info=True)
        out = {"status": ERROR, "result": "That action could not be completed.",
               "code": "interface_error"}
    finally:
        _confirm.consume(user, confirmation_id, status="resolved", choice=key)  # single-use

    out["confirmation_id"] = confirmation_id
    record_tool_call(
        user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
        args={k: v for k, v in params.items() if k != "confirmed"},
        result_status=out["status"], conversation_id=conversation_id,
        result_digest={"confirmation_id": confirmation_id, "choice": key,
                       "result": out.get("result", "")},
    )
    return out


def _find_option(rec, key):
    """Locate an explicit N-way action option (by key) in the stored view, or None."""
    actions = ((rec.get("view") or {}).get("actions")) or {}
    for a in [actions.get("primary")] + list(actions.get("secondary") or []):
        if isinstance(a, dict) and a.get("key") == key:
            return a
    return None


def resolve_typed_confirmation(user, conversation_id, message, *, turn_id="",
                               surface="") -> "dict | None":
    """Deterministically resolve a TYPED confirm/cancel against the open confirmation bound to
    this conversation — the eliminate-the-class fix so a plain 'yes'/'import'/'cancel' can NEVER
    be lost to model interpretation. Returns the resolve result (with `confirmation_id`), or
    None when there is no open confirmation or the message doesn't clearly match one — in which
    case the normal model path handles it (it still sees pending_confirmations)."""
    try:
        from apps.ai.confirmation_contract import match_typed
        for rec in _confirm.open_for_conversation(user, conversation_id):
            key = match_typed(message, rec.get("view"))
            if key:
                return resolve_pending_action(
                    user, rec.get("id"), choice=key,
                    confirm=(key != "cancel"), turn_id=turn_id, surface=surface)
    except Exception:  # pragma: no cover - never break a turn
        logger.warning("action_interface.resolve_typed failed user=%s",
                       getattr(user, "id", "?"), exc_info=True)
    return None
