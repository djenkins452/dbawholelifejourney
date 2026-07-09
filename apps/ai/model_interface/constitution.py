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
    "CURRENT CONTEXT: You are given a small always-on baseline (clock, day-continuity, "
    "clinical-safety priority, and what WLJ can answer). Honor the deterministic priority "
    "order — do not re-rank it. Anything deeper about the user's life is NOT pushed to "
    "you; pull it with a truth tool when the conversation calls for it. For general or "
    "outside-work topics, simply do not pull personal truth.\n"
    "\n"
    "ACTIONS: You never change the user's data directly. Request an action; WLJ executes "
    "it and returns the real result, which you then communicate. Destructive or ambiguous "
    "actions require confirmation — after the user confirms, resolve the pending action."
)


# Minimal Day-1 tool set (Slice 7): three truth reads + the two action calls.
TRUTH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_domain_state",
            "description": (
                "Get the current deterministic WLJ state for one life domain "
                "(e.g. health, finance, goals, calendar). Returns truth-envelope data "
                "with freshness/confidence/source. Pull this when the conversation needs "
                "the user's current state in a domain."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string",
                               "description": "The life domain to read."},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": (
                "Search the user's WLJ history (journal, notes, past records) for a "
                "query, optionally within a timeframe. Returns audited truth-envelope "
                "data. Pull this when the conversation references the past."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "timeframe": {"type": "string",
                                  "description": "Optional natural timeframe, e.g. "
                                                 "'last week'."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_foundational_health_facts",
            "description": (
                "Get foundational, canonical health facts (e.g. current medications, "
                "latest weight, protein target). Returns truth-envelope data. Pull this "
                "when the conversation needs the user's core health facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"},
                             "description": "Optional specific fact keys to fetch."},
                },
            },
        },
    },
]

ACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "request_action",
            "description": (
                "Request that WLJ perform an action on the user's data (create/update/"
                "log). WLJ executes it safely and returns the real result. If it needs "
                "confirmation, WLJ holds it and returns confirmation_required — confirm "
                "with the user, then call resolve_pending_action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "description": "The action/intent type."},
                    "params": {"type": "object",
                               "description": "Parameters for the action."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_pending_action",
            "description": (
                "Resolve the action WLJ is holding for confirmation. Set confirm=true to "
                "execute the stored action, or confirm=false to cancel it. WLJ held the "
                "action — you do not need to restate it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean"},
                },
                "required": ["confirm"],
            },
        },
    },
]


def all_tools():
    """The full minimal Slice-7 tool set (truth + action)."""
    return list(TRUTH_TOOLS) + list(ACTION_TOOLS)
