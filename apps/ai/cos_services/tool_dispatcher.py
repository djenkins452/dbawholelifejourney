# ==============================================================================
# File: apps/ai/cos_services/tool_dispatcher.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ChatGPT CoS tool dispatcher (Phase 3) — deterministic, no logic
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
ChatGPT CoS Tool Dispatcher (Phase 3)
=====================================

Deterministic routing only: receive a tool request -> validate -> execute the
bound handler -> return a JSON-safe envelope. NO business logic lives here — every
handler delegates to an existing deterministic service (Phase 1/2 today).

    dispatch_tool_call(user, name, arguments) -> dict

Envelope: { tool, ok, result | error, code }. The dispatcher NEVER raises into
the caller (the OpenAI tool loop) — a failed tool returns ok=False with a code,
so the model can narrate the gap rather than the request crashing. No silent
failures: every error path is logged + telemetered.
"""

import logging
import time

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe
from apps.ai.cos_services.tool_registry import get_tool

logger = logging.getLogger(__name__)

# Cap the serialized tool result handed back to the model (token safety).
_MAX_RESULT_CHARS = 8000


def _emit(user_id, name, ok, code, ms):
    try:
        logger.info(
            "COS_TOOL dispatch user=%s tool=%s ok=%s code=%s ms=%s",
            user_id, name, ok, code, ("%.1f" % ms) if ms is not None else "na",
        )
    except Exception:
        pass


def _envelope(name, ok, *, result=None, error=None, code=None):
    env = {"tool": name, "ok": ok}
    if ok:
        env["result"] = result
    else:
        env["error"] = error
        env["code"] = code
    return env


def dispatch_tool_call(user, name, arguments):
    """
    Execute one CoS tool call deterministically.

    Args:
        user: Django User instance.
        name: tool name (must be a registered, enabled tool).
        arguments: dict of tool arguments (already JSON-parsed).

    Returns:
        dict envelope (always JSON-safe; never raises).
    """
    t0 = time.monotonic()
    uid = getattr(user, "id", "?")
    args = arguments if isinstance(arguments, dict) else {}

    entry = get_tool(name)

    # --- unknown tool ---
    if entry is None:
        _emit(uid, name, False, "unknown_tool", (time.monotonic() - t0) * 1000)
        return _envelope(name, False, error="Unknown tool.", code="unknown_tool")

    # --- registered but not yet enabled (later phase) ---
    if not entry.get("enabled") or entry.get("handler") is None:
        _emit(uid, name, False, "tool_not_enabled", (time.monotonic() - t0) * 1000)
        return _envelope(
            name, False,
            error="Tool is registered but not enabled yet (later rollout phase).",
            code="tool_not_enabled",
        )

    # --- execute (handler delegates to an existing deterministic service) ---
    try:
        raw = entry["handler"](user, **args)
        result = _jsonsafe(raw)
        # token-safety cap on the serialized result
        import json as _json
        if len(_json.dumps(result)) > _MAX_RESULT_CHARS:
            result = {
                "_truncated": True,
                "_note": "Result exceeded size budget; request a narrower domain.",
                "status": result.get("status") if isinstance(result, dict) else None,
            }
        _emit(uid, name, True, "ok", (time.monotonic() - t0) * 1000)
        return _envelope(name, True, result=result)
    except TypeError as exc:
        # bad/missing arguments from the model
        logger.warning("COS_TOOL bad args tool=%s user=%s: %s", name, uid, exc)
        _emit(uid, name, False, "bad_arguments", (time.monotonic() - t0) * 1000)
        return _envelope(name, False, error="Invalid tool arguments.",
                         code="bad_arguments")
    except Exception as exc:  # never swallow silently; never crash the loop
        logger.warning("COS_TOOL exec failed tool=%s user=%s", name, uid,
                       exc_info=True)
        _emit(uid, name, False, "execution_error", (time.monotonic() - t0) * 1000)
        return _envelope(name, False, error="Tool execution failed.",
                         code="execution_error")
