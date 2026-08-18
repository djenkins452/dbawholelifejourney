# ==============================================================================
# File: apps/ai/cos_services/action_execution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ActionExecutionService (Phase 6) — ChatGPT CoS write surface
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
ActionExecutionService (ChatGPT CoS — Phase 6)
==============================================

The single write surface for the ChatGPT reasoning layer:

    execute_action(user, action, params)

ChatGPT NEVER writes directly. It REQUESTS execution; WLJ executes
deterministically through the EXISTING single write path:

    execute_action()  ->  IntentService.execute_intent()  ->  UAIO  ->  handler

REUSE ONLY (per the Readiness Audit's 54 existing deterministic handlers):
* `apps.ai.intent_service.IntentService.execute_intent(IntentResult, user)` — the
  sole dispatcher; its fail-closed Learning-Mode gate is preserved automatically.
* `apps.core.ai_orchestrator.action_policy.ACTION_POLICY` — the EXISTING governance
  metadata (category + risk). We read it to decide confirmation; we do NOT build a
  new policy/confirmation system.

NO new write path, NO new action framework, NO parallel execution, NO direct
model writes, NO bypassing UAIO or the existing safety gates.

Safety design:
* STRICT Day-1 allowlist — only non-destructive create/log/complete actions.
* Confirmation gate — destructive (DESTRUCTIVE category) or HIGH/CRITICAL-risk
  actions require an explicit `confirmed=true` (the model asks the user first);
  routine creates/logs/completes execute directly (Phase-6 spec threshold).
* Never raises into the caller (the tool loop). Returns a structured, JSON-safe
  result envelope. No silent failures — every path is logged + telemetered.
"""

import logging
import time

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

ACTION_EXECUTION_SCHEMA_VERSION = "1.0"

# Strict Day-1 allowlist — intent_type strings the dispatcher (execute_intent)
# already accepts, restricted to safe create/log/complete/mutate actions.
# NOTE: 'update_task' -> 'mutate_task', 'update_goal' -> 'update_goal_progress'.
# 'create_note'/'create_capture' are app-level (NOT intent types) -> excluded.
DAY1_ACTION_ALLOWLIST = {
    "create_task",
    "mutate_task",          # update_task
    "complete_task",
    "create_goal",
    "update_goal_progress",  # update_goal
    "create_journal_entry",
    "add_gratitude",
    "log_prayer",
    "save_verse",
    "create_event",
    "add_reminder",
    "log_habit",
    "log_workout",
    "log_weight",
    "log_body_measurements",   # import a full body check-in from a screenshot/photo/typed set
    "import_journal_entries",  # Structured Import: one document → many journal entries
}

# Intents that decide confirmation from the CANDIDATE DATA (not a static per-action policy) —
# e.g. multimodal writes confirm on low perception confidence / suspected duplicate. For these,
# `confirmed=true` must reach the handler so a confirmed re-execution BYPASSES the data gate
# (otherwise it would loop). Single source of truth: apps/ai/multimodal.DATA_CONFIRM_INTENTS
# (also honoured by the deterministic bare-"yes" replay in intent_service.handle_crud_confirmation).
from apps.ai.multimodal import DATA_CONFIRM_INTENTS as _DATA_CONFIRM_INTENTS


def allowed_actions():
    return sorted(DAY1_ACTION_ALLOWLIST)


# Model-facing writes that are intrinsically low-risk AND reversible through a canonical
# inverse. They still obey `assistant_confirm_actions`; this only says they carry no
# independent risk that would force confirmation when the user has not asked for it.
REVERSIBLE_MODEL_INTERFACE_WRITES = frozenset({"complete_execution_item"})


def confirmation_required_for(user, action, *, state_changing=True):
    """THE confirmation policy for CoS writes. ONE authority; every state-changing
    model-facing action consults this, and none implements its own check.

    Two independent grounds, either sufficient:
      1. the USER'S PREFERENCE `assistant_confirm_actions` ("Ask me first before
         creating, changing or deleting anything on my behalf");
      2. the action's own risk policy (destructive / high-risk / explicit-verb).

    (1) was previously enforced ONLY inside `IntentService.recognize_intents`, which the
    certified model_interface runtime does not use — the model selects tools directly. So
    a user with the preference ON had it delivered into the envelope (M1 T3) but NEVER
    enforced at the write boundary. Proven 2026-08-18: ToolCallLog 62d315f8 shows
    `complete_execution_item` executing straight to `recorded` with the preference ON.

    Delivery is not enforcement. This function is the enforcement.
    """
    if state_changing:
        try:
            if bool(getattr(user.preferences, "assistant_confirm_actions", False)):
                return True
        except Exception:  # pragma: no cover - defensive; fail SAFE toward confirming
            logger.warning("action_execution: confirm-preference read failed user=%s",
                           getattr(user, "id", None), exc_info=True)
            return True
    # Model-interface tools are not DAY1 intents, so they have no ACTION_POLICY row and
    # would hit the unknown-action safe default (always confirm). Register their intrinsic
    # risk explicitly, so the USER'S PREFERENCE is what decides for them: with the
    # preference OFF a reversible completion executes directly (preserving the guided
    # review flow); with it ON, the branch above already required confirmation.
    if action in REVERSIBLE_MODEL_INTERFACE_WRITES:
        return False
    return _confirmation_required(action)


def _confirmation_required(action):
    """Reuse ACTION_POLICY metadata; apply the Phase-6 CoS threshold:
    destructive category OR high/critical risk OR explicit-verb actions need
    confirmation. Unknown action -> require confirmation (safe default)."""
    try:
        from apps.core.ai_orchestrator.action_policy import (
            ACTION_POLICY,
            ActionCategory,
            RiskLevel,
        )
    except Exception:
        return True  # if policy unavailable, fail safe -> confirm
    policy = ACTION_POLICY.get(action)
    if policy is None:
        return True
    if policy.category == ActionCategory.DESTRUCTIVE:
        return True
    if policy.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return True
    if getattr(policy, "requires_explicit_verb", False):
        return True
    return False


def _emit(user_id, action, status, *, code=None, ms=None):
    """Observable telemetry. No silent failures."""
    try:
        logger.info(
            "COS_ACTION user=%s action=%s status=%s code=%s ms=%s",
            user_id, action, status, code,
            ("%.1f" % ms) if ms is not None else "na",
        )
    except Exception:
        pass


def _envelope(action, status, **extra):
    env = {
        "status": status,
        "action": action,
        "schema_version": ACTION_EXECUTION_SCHEMA_VERSION,
    }
    env.update(extra)
    return env


def execute_action(user, action, params):
    """
    Execute one write action on the user's behalf, deterministically.

    Args:
        user: Django User instance.
        action: intent_type string (must be in DAY1_ACTION_ALLOWLIST).
        params: dict of handler parameters. A truthy `confirmed` key authorizes
            actions that require confirmation (it is stripped before dispatch).

    Returns:
        dict envelope (always JSON-safe; never raises). `status` is one of:
            "success"               — action executed
            "failed"                — handler returned success=False (e.g. not found,
                                      learning-mode active)
            "denied"                — action not in the allowlist
            "confirmation_required" — needs explicit confirmed=true first
            "error"                 — execution raised (logged)
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    action_norm = (action or "").strip().lower()
    params = dict(params) if isinstance(params, dict) else {}
    confirmed = bool(params.pop("confirmed", False))

    _emit(uid, action_norm, "requested")

    # 1. allowlist gate
    if action_norm not in DAY1_ACTION_ALLOWLIST:
        _emit(uid, action_norm, "denied", code="not_allowlisted",
              ms=(time.monotonic() - t0) * 1000)
        return _envelope(
            action_norm, "denied",
            message="That action is not enabled for the assistant.",
            code="not_allowlisted",
            allowed_actions=allowed_actions(),
        )

    # 2. confirmation gate (reuses ACTION_POLICY risk/category metadata)
    if confirmation_required_for(user, action_norm) and not confirmed:
        _emit(uid, action_norm, "confirmation_required",
              ms=(time.monotonic() - t0) * 1000)
        return _envelope(
            action_norm, "confirmation_required",
            message=(
                "This action changes existing data and needs confirmation. "
                "Confirm with the user, then re-call with confirmed=true."
            ),
            code="confirmation_required",
        )

    # 3. execute through the SINGLE existing write path (UAIO). For data-confirm intents,
    #    forward `confirmed` so a confirmed re-execution skips the handler's own data gate.
    if confirmed and action_norm in _DATA_CONFIRM_INTENTS:
        params["confirmed"] = True
    try:
        from apps.ai.intent_service import IntentResult, IntentService
        intent = IntentResult(intent_type=action_norm, parameters=params,
                              confidence=1.0)
        result = IntentService().execute_intent(intent, user)
    except Exception as exc:
        logger.warning("COS_ACTION exec raised action=%s user=%s",
                       action_norm, uid, exc_info=True)
        _emit(uid, action_norm, "error", code="execution_error",
              ms=(time.monotonic() - t0) * 1000)
        return _envelope(action_norm, "error",
                         message="Action execution failed; see server logs.",
                         code="execution_error")

    # 4. ActionResult -> JSON-safe envelope
    success = bool(getattr(result, "success", False))
    err = getattr(result, "error", None)
    ms = (time.monotonic() - t0) * 1000

    # A handler may compute confirmation from the CANDIDATE DATA (e.g. a low-confidence or
    # duplicate multimodal write). That is deterministic WLJ policy, not a failure — surface
    # it as confirmation_required so the interface mints a BOUND confirmation and the user is
    # asked first. On the confirmed re-run, `confirmed=true` (step 3) bypasses this gate.
    if not success and err == "confirmation_required":
        _emit(uid, action_norm, "confirmation_required", ms=ms)
        # The generic import-confirmation framework owns PRESENTATION: if the handler returned a
        # structured confirmation_detail with a registered renderer, render it into the RESULTS-
        # not-intentions summary the user sees. Otherwise fall back to the handler's own message.
        rendered = None
        try:
            from apps.ai.import_confirmation import render_import_confirmation
            rendered = render_import_confirmation(getattr(result, "confirmation_detail", None))
        except Exception:  # pragma: no cover - presentation must never block a confirmation
            logger.warning("COS_ACTION confirmation render failed action=%s user=%s",
                           action_norm, uid, exc_info=True)
        return _envelope(
            action_norm, "confirmation_required",
            message=(rendered or getattr(result, "message", "") or
                     "This needs your confirmation before I log it."),
            code="confirmation_required",
            # Structured preview for the Rich Confirmation view (title/summary/preview/actions).
            confirmation_detail=getattr(result, "confirmation_detail", None),
        )

    _emit(uid, action_norm, "executed" if success else "failed",
          code=err, ms=ms)
    return _envelope(
        action_norm,
        "success" if success else "failed",
        message=getattr(result, "message", ""),
        result=_jsonsafe(getattr(result, "created_object", None)),
        error=err,
        # Structured EVIDENCE from the handler (2026-08-18 incident). Carries machine-
        # checkable facts about a failure — notably `establishes_absence` — so the
        # continuation can tell "this handler did not match" from "WLJ has no such object".
        evidence=_jsonsafe(getattr(result, "data", None)),
        _meta={"duration_ms": round(ms, 1)},
    )
