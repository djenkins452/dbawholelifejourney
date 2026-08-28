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


def _authorization_notice(authorization, fallback_message):
    """The confirmation text handed to the model.

    It leads with the DETERMINISTIC authorization line and states plainly that the line
    may be explained but not redefined. The model owns how it introduces a pending
    action; it does not own what the action IS.
    """
    if not authorization:
        return fallback_message or "Please confirm."
    return (f"AWAITING AUTHORIZATION — this will do exactly: {authorization}. "
            f"Tell the user precisely this before asking them to confirm; you may add "
            f"context, but never describe it as a different action, a different domain, "
            f"or different values. If that is not what they asked for, say so instead of "
            f"asking them to confirm it.")


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
        # The VIEW is not decoration — it carries the action aliases that
        # `confirmation_contract.match_typed` matches a typed "yes"/"no" against, and it
        # is what the deterministic pre-parser in cos_gateway.runtime uses to resolve a
        # confirmation WITHOUT the model. Omitting it (as this function first did) made
        # `match_typed` return None immediately, so a plain "Yes" silently fell through
        # to the model — which then narrated a completion it never executed
        # (production 2026-08-18, turn 48957246: zero tool calls).
        try:
            from apps.ai.confirmation_contract import build_view
            view = build_view(action, params, None, summary=summary)
        except Exception:  # pragma: no cover
            logger.warning("action_interface: build_view failed action=%s", action,
                           exc_info=True)
            view = None
        if not view:
            # FAIL CLOSED: no deterministic presentation of this action exists, so there
            # is no honest way to ask the user to authorize it. Refusing beats showing an
            # ambiguous confirmation the user cannot evaluate.
            logger.warning("action_interface: no deterministic view for action=%s — "
                           "refusing to request confirmation", action)
            return None
        handle = _confirm.create(user, action, params, summary, view=view,
                                 conversation_id=conversation_id)
        if not handle:
            return None
        rec = _confirm.get(user, handle["confirmation_id"])
        out = {
            "status": CONFIRMATION_REQUIRED,
            "result": _authorization_notice(handle.get("authorization"), summary),
            "authorization": handle.get("authorization"),
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
        if out["status"] in (CONFIRMATION_REQUIRED, ERROR) and env.get("validation"):
            # AUDIT: the deterministic validation outcome — proposed value/unit, the
            # comparison drawn from canonical history, the thresholds applied, and
            # whether exceptional authorization was required — travels with the result
            # so a blocked or exceptional write is fully reconstructable.
            out["validation"] = env["validation"]
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
                # WHAT THE MODEL IS TOLD IS WHAT WAS BOUND. The handler's own message may
                # introduce the action, but the authorization line is rendered from the
                # bound (action, params) and is the only description of what will happen.
                # Production 2026-08-27: a `create_task` confirmation was narrated to the
                # user as "ready to log Stuffed Peppers for dinner", so the user
                # authorized something they were never shown.
                out["result"] = _authorization_notice(handle.get("authorization"),
                                                      env.get("message") or summary)
                out["authorization"] = handle.get("authorization")
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
                       "confirmation_id": (out.get("confirmation") or {}).get("confirmation_id"),
                       # M2 audit: a blocked or exceptional measurement write records the
                       # proposed value/unit, the canonical comparison, the thresholds and
                       # whether exceptional authorization was required.
                       **({"validation": out["validation"]} if out.get("validation") else {})},
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
    # Peek FIRST so a cancel can be handled without burning the exactly-once claim, and
    # so a replay is distinguishable from an expiry.
    rec = _confirm.get(user, confirmation_id)
    key = (choice or ("confirm" if confirm else "cancel"))
    is_cancel = (key == "cancel") or (confirm is False and not choice)

    if not rec:
        tomb = _confirm.peek(user, confirmation_id)
        status_now = (tomb or {}).get("status")
        if status_now == "resolved":
            # REPLAY, NEVER RE-EXECUTE. The single execution's result was stored on the
            # authorization row, so a repeated "confirm" (a retry, a double-send, a
            # reconnect) returns what actually happened instead of mutating again — the
            # defect that produced two identical weight rows from one confirmation.
            prior = (tomb or {}).get("result") or {}
            out = {"status": prior.get("status") or OK,
                   "result": prior.get("result") or "That was already done.",
                   "code": "already_resolved", "replayed": True,
                   "confirmation_id": confirmation_id}
            record_tool_call(user, kind="action", tool_name=(tomb or {}).get("action", ""),
                             turn_id=turn_id, surface=surface, result_status=out["status"],
                             conversation_id=conversation_id,
                             result_digest={"confirmation_id": confirmation_id,
                                            "code": "already_resolved", "replayed": True,
                                            "mutated": False})
            return out
        if status_now == "executing":
            # FAIL CLOSED: another consumer holds the claim (or a write crashed
            # mid-flight). Never race it — a duplicate write is worse than a retry.
            code, msg = ("already_resolved",
                         "That confirmation is already being carried out.")
        elif status_now == "cancelled":
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
                         result_digest={"confirmation_id": confirmation_id, "code": code,
                                        "mutated": False})
        return out

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
        _confirm.finalize(user, confirmation_id, status="cancelled", choice="cancel")
        out = {"status": DECLINED, "result": "Okay — I won't do that.",
               "confirmation_id": confirmation_id}
        record_tool_call(user, kind="action", tool_name=action, turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         conversation_id=conversation_id,
                         result_digest={"confirmation_id": confirmation_id, "declined": True})
        return out

    # ── THE EXACTLY-ONCE GATE ────────────────────────────────────────────────────
    # Atomically move pending → executing. Only the single winner may mutate anything;
    # every other caller (a second confirm, a concurrent request, a retry during a cache
    # outage) loses the compare-and-swap and is turned away WITHOUT executing. This is a
    # database-evaluated conditional UPDATE, so it holds even when Redis is down — the
    # previous cache `consume()` failed open and let one authorization write twice.
    claimed = _confirm.claim(user, confirmation_id)
    if claimed is None:
        out = {"status": ERROR, "code": "already_resolved",
               "result": "That confirmation was already handled.",
               "confirmation_id": confirmation_id}
        record_tool_call(user, kind="action", tool_name=action, turn_id=turn_id,
                         surface=surface, result_status=out["status"],
                         conversation_id=conversation_id,
                         result_digest={"confirmation_id": confirmation_id,
                                        "code": "claim_lost", "mutated": False})
        return out
    # Execute EXACTLY the payload the claim returned — the bound action and arguments the
    # user was shown, never re-derived from a name or from current conversation state.
    action = claimed.get("action", action)
    params = dict(claimed.get("params") or {})
    chosen = _find_option(claimed, key) if (key not in ("confirm", "cancel")) else None
    if chosen:
        action = chosen.get("action") or action
        if isinstance(chosen.get("params"), dict):
            params.update(chosen["params"])
        else:
            params["choice"] = key
    params["confirmed"] = True
    # `complete_execution_item` is a model-interface tool, not a DAY1 intent, so it is not
    # dispatchable by `execute_action`. Route the CONFIRMED action back to the completion
    # service with the EXACT bound params — the target is never re-resolved from a name or
    # from whatever the current action happens to be by now.
    if action == "delete_record":
        # The CONFIRMED removal executes the identity that was BOUND at confirmation
        # time — never a target re-resolved from a name, a description, or whatever the
        # most recent record happens to be by now.
        from apps.ai.cos_services import record_correction as _rc
        done = _rc.remove_record(user, params.get("record_type"),
                                 params.get("record_id"))
        ok = done.get("status") in (_rc.OK, _rc.ALREADY_REMOVED)
        out = {"status": OK if ok else ERROR, "result": done.get("message"),
               "code": None if ok else done.get("status"),
               "evidence": {k: done.get(k) for k in
                            ("record_type", "record_id", "removed", "description")}}
        _confirm.finalize(user, confirmation_id, status="resolved", choice="confirm",
                          result={"status": out["status"], "result": out["result"]})
        record_tool_call(
            user, kind="action", tool_name=action, turn_id=turn_id, surface=surface,
            args=params, result_status=done.get("status", ""),
            conversation_id=conversation_id,
            result_digest={"status": done.get("status"), "confirmed": True,
                           "confirmation_id": confirmation_id,
                           "removed": done.get("removed"),
                           "record_type": done.get("record_type"),
                           "record_id": done.get("record_id"),
                           "description": done.get("description")})
        return out
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
            ok = done.get("status") in ("recorded", "already_complete", "reversed")
            out = {"status": OK if ok else ERROR,
                   "result": done.get("message") or done.get("status"),
                   "code": None if ok else done.get("status"),
                   "evidence": done.get("detail") or {}}
            # Store the outcome ON the authorization row so a retry REPLAYS it.
            _confirm.finalize(user, confirmation_id, status="resolved", choice="confirm",
                              result={"status": out["status"], "result": out["result"]})
            # AUDITABILITY (write-surface audit, 2026-08-19). This branch returns before
            # the function's trailing record_tool_call, so the CONFIRMED EXECUTION — the
            # turn that actually mutates — left no audit row. Production 2026-08-19 shows
            # `confirmation_required` and a later `reversed`, with the successful
            # completion between them missing entirely. Every write must be
            # reconstructable: tool, args, requested target, resolved identity,
            # confirmation state, result.
            record_tool_call(
                user, kind="action", tool_name=action, turn_id=turn_id,
                surface=surface, args=params, result_status=done.get("status", ""),
                conversation_id=conversation_id,
                result_digest={"status": done.get("status"),
                               "message": (done.get("message") or "")[:200],
                               "confirmation_id": confirmation_id,
                               "confirmed": True,
                               "source_type": params.get("source_type"),
                               "source_id": params.get("source_id"),
                               "requested_target": params.get("title"),
                               "detail": done.get("detail") or {}},
            )
            return out
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
        # The claim is already spent; record the OUTCOME so a repeat confirm replays the
        # real result instead of mutating again. Always runs — a crash still leaves the
        # confirmation terminal rather than re-executable.
        _confirm.finalize(user, confirmation_id, status="resolved", choice=key,
                          result={"status": out.get("status"),
                                  "result": out.get("result")})

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
