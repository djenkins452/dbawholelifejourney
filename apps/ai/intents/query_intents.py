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
                "Query the user's data to look up specific values, find what happened, "
                "what is scheduled, what was missed, or when something occurred. Use "
                "when the user asks about events (past OR future), specific data "
                "points, scheduled/planned items, missed items, or execution history "
                "across ANY domain. "
                "Covers: medication, sleep, weight, glucose, blood pressure, heart rate, "
                "steps, water, nutrition/food, fasting, workouts, routines, journal, "
                "faith/prayer, habits, and finance. "
                "Examples (past): 'how did I sleep last night?', 'what was my blood "
                "pressure?', 'what did I miss this week?', 'what did I eat yesterday?', "
                "'how many steps did I get?', 'how was my glucose after lunch?', "
                "'did I journal yesterday?'. "
                "Examples (future/scheduled): 'what is my workout tomorrow?', "
                "'what's my next workout?', 'what's planned for tomorrow?', "
                "'do I have a workout scheduled tomorrow?'. "
                "Do NOT use for action requests (logging, creating, marking complete) — "
                "this is read-only data lookup."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["lookup", "missed", "timeline", "slippage", "general"],
                        "description": (
                            "Type of query: "
                            "'lookup' = retrieve specific data points ('how was my sleep?', "
                            "'what's my weight?', 'blood pressure reading?'), "
                            "'missed' = what was missed/skipped (medication, routine, etc.), "
                            "'timeline' = what happened on a specific date, "
                            "'slippage' = when did a pattern start declining, "
                            "'general' = other data history question"
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "enum": [
                            "medication", "routine", "workout",
                            "sleep", "weight", "glucose", "blood_pressure",
                            "heart_rate", "steps", "water", "nutrition",
                            "fasting", "journal", "faith", "habits",
                            "finance", "body_composition", "all",
                        ],
                        "description": (
                            "Which domain to query. Match to data type: "
                            "'sleep' for sleep/rest, 'weight' for weight/scale, "
                            "'glucose' for blood sugar/glucose/CGM, "
                            "'blood_pressure' for BP readings, "
                            "'heart_rate' for pulse/HR/bpm, "
                            "'steps' for step count/walking/activity, "
                            "'water' for hydration/water intake, "
                            "'nutrition' for food/meals/calories/macros, "
                            "'fasting' for intermittent fasting, "
                            "'medication' for meds/doses/pills, "
                            "'workout' for exercise/gym/training, "
                            "'routine' for daily routines, "
                            "'journal' for journal entries/mood, "
                            "'faith' for prayer/Bible reading, "
                            "'habits' for habit tracking, "
                            "'finance' for spending/transactions/budget, "
                            "'body_composition' for body measurements: "
                            "waist, chest, arms, forearms, thighs, calves, "
                            "hips, neck, shoulders, body fat %, lean mass, "
                            "fat mass, BMI, BMR. Use for 'measurements', "
                            "'compare to last time', 'how did my waist change?', "
                            "'what are my latest measurements?'. "
                            "'all' for cross-domain or unclear."
                        ),
                    },
                    "lookback_days": {
                        "type": "integer",
                        "description": (
                            "How many days back to search. Default 7. "
                            "Use 1 for 'today'/'last night', "
                            "2 for 'yesterday and today', "
                            "7 for 'this week', "
                            "14 for 'two weeks'. Max 30."
                        ),
                    },
                    "target_date": {
                        "type": "string",
                        "description": (
                            "Specific date for timeline or lookup queries. "
                            "Accepts past, present, or future dates: "
                            "'today', 'yesterday', 'tomorrow', 'last night', "
                            "a day name like 'monday' or 'next monday', "
                            "or a YYYY-MM-DD date (past OR future)."
                        ),
                    },
                    "count": {
                        "type": "integer",
                        "description": (
                            "Number of recent entries to return for lookup queries. "
                            "Default 1 for 'latest' questions, up to 10 for 'recent' questions."
                        ),
                    },
                },
                "required": ["query_type", "domain"],
            },
        },
    },
]
