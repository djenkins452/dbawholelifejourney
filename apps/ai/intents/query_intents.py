# ==============================================================================
# File: apps/ai/intents/query_intents.py
# Project: Whole Life Journey — Django 5.x Personal Wellness/Journaling App
# Description: Cross-domain event query intents (read-only)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-28
# ==============================================================================
"""
Cross-Domain Event Query Intents.

These intents allow the user to query event-level execution history
across all domains through natural language. The LLM classifies the
query type and parameters; the deterministic Event Access Layer provides
the factual answer.

Architecture:
    User message → LLM classifies as query_event_history
    → ActionHandler.handle_query_event_history()
    → EventResolver queries canonical domain models
    → Deterministic response (no LLM-generated facts)
"""

QUERY_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_event_history",
            "description": (
                "Query the user's event history to find what happened, what was "
                "missed, or when something occurred. Use when the user asks about "
                "past events, missed items, or execution history across any domain "
                "(medication, routines, workouts, etc.). "
                "Examples: 'what did I miss this week?', 'which medication did I "
                "miss and when?', 'it says I missed 5 doses, what are they?', "
                "'what happened yesterday?', 'when did my routine start slipping?'. "
                "Do NOT use for action requests (logging, marking complete, etc.) — "
                "this is read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["missed", "timeline", "slippage", "general"],
                        "description": (
                            "Type of event query: "
                            "'missed' = what was missed/skipped (medication, routine, etc.), "
                            "'timeline' = what happened on a specific date, "
                            "'slippage' = when did a pattern start declining, "
                            "'general' = other event history question"
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "enum": [
                            "medication", "routine", "workout",
                            "all",
                        ],
                        "description": (
                            "Which domain to query. Use 'medication' for doses/meds/pills, "
                            "'routine' for routine items/habits, 'workout' for exercise sessions, "
                            "'all' for cross-domain queries or when domain is unclear."
                        ),
                    },
                    "lookback_days": {
                        "type": "integer",
                        "description": (
                            "How many days back to search. Default 7. "
                            "Use 1 for 'today', 2 for 'yesterday and today', "
                            "7 for 'this week', 8 for '8 days' (as shown on dashboard), "
                            "14 for 'two weeks'. Max 30."
                        ),
                    },
                    "target_date": {
                        "type": "string",
                        "description": (
                            "Specific date for timeline queries. "
                            "Use 'today', 'yesterday', a day name like 'monday', "
                            "or YYYY-MM-DD format."
                        ),
                    },
                },
                "required": ["query_type"],
            },
        },
    },
]
