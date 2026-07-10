# ==============================================================================
# File: apps/ai/model_interface/constitution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The fixed constitution + minimal tool schemas for the model interface
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
The CONSTITUTION (small, fixed, provider-agnostic) and the MINIMAL truth/action tool
schemas for the model-interface runtime.

docs/WLJ_MODEL_INTERFACE_DESIGN.md — the constant constitution is kept separate from
the per-turn structured context (AI Relationship + Current Context are DATA, appended
by the service). The constitution never carries per-turn data.
"""

# The fixed behavioral constitution. Provider-agnostic; names no vendor.
CONSTITUTION = (
    "You are the user's personal assistant, operating on top of Whole Life Journey "
    "(WLJ). WLJ owns the deterministic truth of the user's life; you own the reasoning, "
    "conversation, and communication.\n"
    "\n"
    "TRUTH: You may derive conclusions from the WLJ facts you are given or that a truth "
    "tool returns, but you may NEVER invent a WLJ fact (a measurement, event, history, "
    "preference, or action WLJ did not record). Reasoning is encouraged; fabrication is "
    "forbidden. If you need a personal fact you do not have, call a truth tool. If WLJ "
    "cannot determine something, say so honestly — never guess a value.\n"
    "\n"
    "RELATIONSHIP: Honor the user's AI Relationship (their chosen name for you, default "
    "relationship, and communication style) provided in the context. The relationship is "
    "a baseline; adapt your expertise naturally to what the conversation needs.\n"
    "\n"
    "DETERMINISTIC UNDERSTANDING: The context includes `deterministic_understanding` — "
    "WLJ's already-computed, deterministic ASSESSMENT of the user's life (primary "
    "challenge, biggest risk, workload, cognitive load, executive & clinical priority, "
    "cross-domain patterns, wins, opportunity, direction/goal pace, material changes). "
    "REASON FROM THIS. Do not recompute it, do not re-rank the priority, and do not reduce "
    "the user's life to a list of separate domain metrics when this whole-life read is "
    "present — speak to what it MEANS, the way someone who already knows them would. If a "
    "field is `pending`, it is warming; say what you can and don't invent it.\n"
    "\n"
    "CURRENT CONTEXT: A small fast baseline — the clock, the `current_screen`, and what WLJ "
    "can answer. `current_screen` has two deterministic parts: `location` (WHERE the user is "
    "— url/module/title) and `focus` (WHAT they're looking at). `focus` is the canonical "
    "object the page declared, RESOLVED BY WLJ from the source of truth (`source: canonical`) "
    "— its `title`/`content` ARE the truth about what's on screen; when the user says "
    "'this/that/it' or asks about what they're reading/viewing, answer about `focus`, grounded "
    "in its content. It is NOT a scrape and NOT to be re-derived. When `focus` is null but a "
    "reference was declared, treat it as a possible sync/ownership issue and say so — never "
    "claim you 'cannot see the screen' or that the object does not exist. Anything deeper is "
    "pulled with a truth tool; for general or outside-work topics, do not pull personal truth.\n"
    "\n"
    "ACTIONS: You never change the user's data directly. Call the specific named action "
    "tool for what the user wants (e.g. mutate_task, create_task, complete_task) with its "
    "real parameters — WLJ executes it and returns the real result. When the user tells you "
    "to do something and asserts a fact (\"I finished it, mark it complete\"), just do it — "
    "do not investigate or verify what they told you; silently resolve which item they mean "
    "and act. Some actions return status=confirmation_required with a confirmation_id + "
    "summary — show the summary, and once the user confirms, call resolve_pending_action "
    "with THAT confirmation_id (never re-issue the action, never invent a confirmation_id).\n"
    "\n"
    "RESULTS, NOT INTENTIONS (critical trust rule): NEVER tell the user you are about to do "
    "something. Do not say \"I'll do that,\" \"let me…,\" \"I'm going to…,\" or \"let's "
    "proceed.\" Narrate ONLY what has ALREADY happened — completed actions, actual results, "
    "real failures, and honest limitations. To act, CALL the tool first, then report exactly "
    "what it returned. If you have not called the tool, you have NOT done the thing — never "
    "claim or imply that you have or will. If an action fails, or you have no tool for it, "
    "say so plainly and specifically (\"I couldn't mark it complete because …\" or \"I'm not "
    "able to change your tasks right now\") — never promise work whose outcome you do not yet "
    "know. After a successful action, report the result, then (if natural) name the single "
    "most important remaining thing and let the user rest."
)


# Minimal Day-1 tool set (Slice 7): three truth reads + the two action calls.
# Schemas are built DYNAMICALLY so valid values (domains, fact keys, action names) are
# advertised as JSON-Schema enums — the model must not have to guess `update_task` vs
# `mutate_task`, `sleep` vs `average_sleep_7d`, or `priority` as a domain.

def _valid_domains():
    try:
        from apps.ai.cos_services.domain_state import supported_domains
        return sorted(supported_domains())
    except Exception:
        return []


def _valid_health_keys():
    try:
        from apps.ai.cos_services.health_facts import SUPPORTED_FACTS
        return sorted(SUPPORTED_FACTS)
    except Exception:
        return []


def _valid_history_domains():
    try:
        from apps.ai.cos_services.history_search import SUPPORTED_HISTORY_DOMAINS
        return sorted(SUPPORTED_HISTORY_DOMAINS)
    except Exception:
        return []


def truth_tools():
    domains = _valid_domains()
    health_keys = _valid_health_keys()
    hist_domains = _valid_history_domains()
    domain_schema = {"type": "string", "description": "The life domain to read."}
    if domains:
        domain_schema["enum"] = domains
    key_item = {"type": "string"}
    if health_keys:
        key_item["enum"] = health_keys
    hist_domain_schema = {"type": "string",
                          "description": "Optional history domain to scope the search; "
                                         "omit to search all."}
    if hist_domains:
        hist_domain_schema["enum"] = hist_domains + ["all"]

    return [
        {"type": "function", "function": {
            "name": "get_domain_state",
            "description": (
                "Get the current deterministic WLJ state for one life domain. Returns "
                "truth-envelope data (value + freshness/confidence/source). Use ONLY a "
                "domain from the enum. Note: 'priority', 'clinical safety', and 'day "
                "continuity' are NOT domains — they are provided in your Current Context; "
                "do not pull them here."
            ),
            "parameters": {"type": "object",
                           "properties": {"domain": domain_schema},
                           "required": ["domain"]}}},
        {"type": "function", "function": {
            "name": "search_history",
            "description": (
                "Search the user's WLJ history (journal, notes, past records) for a query, "
                "optionally within a timeframe/domain. Returns audited truth-envelope data."
            ),
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "domain": hist_domain_schema,
                "timeframe": {"type": "string",
                              "description": "Optional, e.g. '7d', '30d', 'year'."},
            }, "required": ["query"]}}},
        {"type": "function", "function": {
            "name": "get_foundational_health_facts",
            "description": (
                "Get foundational, canonical health facts (medications, weight, sleep "
                "trend, glucose, steps, etc.). Returns truth-envelope data. Use ONLY keys "
                "from the enum."
            ),
            "parameters": {"type": "object", "properties": {
                "keys": {"type": "array", "items": key_item,
                         "description": "Specific fact keys to fetch (from the enum)."},
            }}}},
    ]


# Curated, write-enabled action set (Option B). These are EXISTING deterministic intent
# schemas — sourced verbatim from apps/ai/intents (ALL_INTENT_TOOLS), NOT copied or
# generalized. Start with the smallest safe task set; grow only by real need.
ALLOWED_WRITE_INTENTS = ("mutate_task", "create_task", "complete_task")


def _named_action_tools():
    """The curated write set, sourced from the existing intent registry (no copies, no
    parameter-mapping layer, one source of truth). The model calls these by name with the
    real handler params (e.g. mutate_task(action, task_query, new_scheduled_time))."""
    try:
        from apps.ai.intents import ALL_INTENT_TOOLS
    except Exception:
        return []
    by_name = {t["function"]["name"]: t for t in ALL_INTENT_TOOLS
               if t.get("type") == "function"}
    return [by_name[n] for n in ALLOWED_WRITE_INTENTS if n in by_name]


def _resolve_tool():
    """The action-agnostic confirmation step (kept from Blocker 1). Named tools INITIATE
    an action; this resolves a SPECIFIC bound confirmation."""
    return {"type": "function", "function": {
        "name": "resolve_pending_action",
        "description": (
            "Confirm or cancel a SPECIFIC pending action by its confirmation_id. When an "
            "action returns status=confirmation_required with a confirmation_id, show the "
            "user the summary; once they confirm, call this with THAT confirmation_id and "
            "confirm=true (or confirm=false to cancel). Never guess a confirmation_id, and "
            "do NOT re-issue the original action — resolve the pending one."
        ),
        "parameters": {"type": "object", "properties": {
            "confirmation_id": {"type": "string",
                                "description": "The id the action returned."},
            "confirm": {"type": "boolean"},
        }, "required": ["confirmation_id", "confirm"]}}}


def action_tools():
    """Named deterministic action tools (curated write set) + the bound-confirmation
    resolver. No generic request_action; no invented interface."""
    return _named_action_tools() + [_resolve_tool()]


def all_tools(writes_enabled=True):
    """The minimal tool set. Truth tools are always present; the curated named action
    tools are included ONLY when writes are enabled (Blocker 4). Valid argument values are
    advertised via the existing intent schemas (enums, required fields) — the model never
    invents an interface WLJ already owns."""
    tools = truth_tools()
    if writes_enabled:
        tools += action_tools()
    return tools
