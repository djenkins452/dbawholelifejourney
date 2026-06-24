# ==============================================================================
# File: apps/ai/cos_services/tool_registry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ChatGPT CoS tool registry (Phase 3) — OpenAI tool schemas + bindings
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
ChatGPT CoS Tool Registry (Phase 3)
===================================

Declares the CoS evidence/action tools the OpenAI reasoning layer may call, as
OpenAI `tools` schemas bound to the EXISTING deterministic services. The registry
is the single extensible source of truth; new tools slot in without redesign.

Each entry: { schema (OpenAI function), handler (callable | None), kind, enabled,
phase }. `enabled=False` tools are registered (so the catalog is complete and
extensible) but are NOT advertised to the model and are rejected by the dispatcher
until their phase lands.

Phase 3 ENABLED: get_standing_context, get_domain_state — these reuse the
Phase 1/2 services and already answer the Phase 3 success-criteria questions
(how am I doing / focus / weight / faith / stalled goals / biggest risk, the last
two via standing context's executive summary).

Registered, DISABLED (later phases): get_decision (Phase 4), search_history
(Phase 5), execute_action (Phase 6 — must route through execute_intent + the
existing safety gates, never around them).

No business logic lives here — handlers delegate to the cos_services functions.
"""

from django.conf import settings

from apps.ai.cos_services.action_execution import allowed_actions as _allowed_actions
from apps.ai.cos_services.domain_state import supported_domains
from apps.ai.cos_services.history_search import SUPPORTED_HISTORY_DOMAINS

ALLOWED_ACTIONS = _allowed_actions()


# ---------------------------------------------------------------------------
# Feature flag (defaults OFF — ships dark, no settings.py change required)
# ---------------------------------------------------------------------------
def evidence_tools_enabled():
    """True when the CoS evidence-tool loop is wired into the answer path."""
    return bool(getattr(settings, "WLJ_COS_EVIDENCE_TOOLS_ENABLED", False))


# ---------------------------------------------------------------------------
# Handlers (thin bindings to existing services — NO business logic)
# ---------------------------------------------------------------------------
def _h_standing_context(user, **kwargs):
    from apps.ai.cos_services.standing_context import get_standing_context
    page_context = kwargs.get("page_context")
    # allow_build stays False: read-only on the request path.
    return get_standing_context(user, page_context=page_context)


def _h_domain_state(user, **kwargs):
    from apps.ai.cos_services.domain_state import get_domain_state
    return get_domain_state(user, kwargs.get("domain", ""))


def _h_execute_action(user, **kwargs):
    from apps.ai.cos_services.action_execution import execute_action
    params = dict(kwargs.get("params") or {})
    if "confirmed" in kwargs:
        params["confirmed"] = kwargs["confirmed"]
    return execute_action(user, kwargs.get("action", ""), params)


def _h_search_history(user, **kwargs):
    from apps.ai.cos_services.history_search import search_history
    return search_history(
        user,
        kwargs.get("query", ""),
        domain=kwargs.get("domain"),
        timeframe=kwargs.get("timeframe"),
    )


def _h_decision(user, **kwargs):
    """Deterministic Execution/Risk/Fix decision — reuses the EXACT pipeline
    behind CosDecisionView (`/assistant/api/cos/decision/`). No new decision
    logic, no LLM: normalize_mode -> build_execution_state -> selectors.select."""
    from apps.ai.cos_mode_router import normalize_mode
    from apps.core.execution.execution_state import build_execution_state
    from apps.core.execution.selectors import select as run_selector

    mode = normalize_mode(kwargs.get("mode", "execution"))
    state = build_execution_state(user)
    decision = run_selector(mode, state)
    return {
        "mode": decision.get("mode"),
        "primary_action": decision.get("primary_action"),
        "reason": decision.get("reason"),
        "follow_on": decision.get("follow_on"),
        "message": decision.get("message"),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
TOOL_REGISTRY = {
    "get_standing_context": {
        "kind": "read",
        "enabled": True,
        "phase": 1,
        "handler": _h_standing_context,
        "schema": {
            "type": "function",
            "function": {
                "name": "get_standing_context",
                "description": (
                    "Return the user's always-loaded Chief-of-Staff standing "
                    "context: current execution summary, top risks, top signals, "
                    "active goals, health headline, situation/mode, and "
                    "recommended focus. Use for holistic 'how am I doing', 'what "
                    "should I focus on', or 'biggest risk' questions. Deterministic."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    },
    "get_domain_state": {
        "kind": "read",
        "enabled": True,
        "phase": 2,
        "handler": _h_domain_state,
        "schema": {
            "type": "function",
            "function": {
                "name": "get_domain_state",
                "description": (
                    "Return canonical deterministic state for one life domain "
                    "(e.g. current weight from 'health', prayer/scripture from "
                    "'faith', stalled goals from 'purpose'). Use when a question "
                    "is about a specific domain. Never fabricate — if the result "
                    "status is 'pending' or 'no_state_source', say so."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "The life domain to read.",
                            "enum": supported_domains(),
                        }
                    },
                    "required": ["domain"],
                },
            },
        },
    },
    "get_decision": {
        "kind": "read",
        "enabled": True,
        "phase": 4,
        "handler": _h_decision,
        "schema": {
            "type": "function",
            "function": {
                "name": "get_decision",
                "description": (
                    "Return WLJ's deterministic decision for one of three modes: "
                    "'execution' (what to do next / focus on now), 'risk' (the "
                    "biggest at-risk item), or 'fix' (what to clean up first). "
                    "WLJ makes the decision from its execution-state pipeline — "
                    "you only explain it. Use for 'what should I focus on', "
                    "'biggest risk', or 'what should I fix first' questions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"mode": {"type": "string",
                                            "enum": ["execution", "risk", "fix"]}},
                    "required": ["mode"],
                },
            },
        },
    },
    # --- registered, disabled until their phase ---
    "search_history": {
        "kind": "read",
        "enabled": True,
        "phase": 5,
        "handler": _h_search_history,
        "schema": {
            "type": "function",
            "function": {
                "name": "search_history",
                "description": (
                    "Search the user's deterministic HISTORY by keyword — past "
                    "journal entries, health records, goals, faith, tasks, "
                    "finance, captures, and notes. Use for 'have I struggled "
                    "with this before', 'what worked previously', 'when did I "
                    "last feel like this', or pattern questions. Omit `domain` "
                    "to search across all. Empty results mean no matching "
                    "history — say so, never invent."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-text search terms.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional single history domain.",
                            "enum": SUPPORTED_HISTORY_DOMAINS,
                        },
                        "timeframe": {
                            "type": "string",
                            "description": (
                                "Optional window: '7d'/'30d'/'90d', "
                                "'week'/'month'/'quarter'/'year', or "
                                "'YYYY-MM-DD:YYYY-MM-DD'."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    },
    "execute_action": {
        "kind": "action",
        "enabled": True,
        "phase": 6,
        "handler": _h_execute_action,
        "schema": {
            "type": "function",
            "function": {
                "name": "execute_action",
                "description": (
                    "Perform a write action on the user's behalf (create a task, "
                    "complete a task, create a goal/journal entry, log a prayer/"
                    "habit/workout, save a verse, schedule an event, add a "
                    "reminder). WLJ executes it deterministically through its "
                    "existing safety-gated pipeline — you only request it. If the "
                    "result status is 'confirmation_required', confirm with the "
                    "user, then re-call with confirmed=true. Report the returned "
                    "message honestly; never claim an action you didn't perform."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "The action to perform.",
                            "enum": ALLOWED_ACTIONS,
                        },
                        "params": {
                            "type": "object",
                            "description": "Handler parameters for the action.",
                        },
                        "confirmed": {
                            "type": "boolean",
                            "description": (
                                "Set true ONLY after the user has confirmed an "
                                "action that requires confirmation."
                            ),
                        },
                    },
                    "required": ["action"],
                },
            },
        },
    },
}


def get_tool(name):
    """Return the registry entry for `name`, or None."""
    return TOOL_REGISTRY.get(name)


def get_tool_schemas(enabled_only=True):
    """Return the OpenAI `tools` array. By default only ENABLED tools are
    advertised to the model (disabled tools stay invisible until their phase)."""
    return [
        entry["schema"]
        for entry in TOOL_REGISTRY.values()
        if entry["schema"] and (entry["enabled"] or not enabled_only)
    ]


def enabled_tool_names():
    return sorted(n for n, e in TOOL_REGISTRY.items() if e["enabled"])
