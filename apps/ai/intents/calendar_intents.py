# ==============================================================================
# File: intents/calendar_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Calendar CRUD intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-23
# ==============================================================================
"""
Calendar Intent Definitions

OpenAI function (tool) definitions for calendar CRUD operations:
- read_calendar_events: Query calendar events (Read)
- mutate_calendar_event: Create, update, or delete calendar events (CUD)
"""

CALENDAR_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_calendar_events",
            "description": (
                "Query the user's calendar to LIST or LOOK UP events. Use ONLY "
                "when the user asks a pure read question: 'what's on my calendar', "
                "'do I have anything scheduled', 'show me my events'. "
                "Do NOT use this for mutation verbs (move, change, reschedule, "
                "update, cancel, delete) — use mutate_calendar_event instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string",
                        "description": (
                            "Search text to match against event titles "
                            "(case-insensitive contains match)"
                        ),
                    },
                    "date_range_start": {
                        "type": "string",
                        "description": (
                            "Start of date range filter. Pass weekday names "
                            "directly (e.g. 'monday', 'wednesday'). PRESERVE "
                            "modifiers: 'next wednesday' = following week, "
                            "'last friday' = most recent past Friday. Also "
                            "accepts 'today', 'tomorrow', 'yesterday', "
                            "'in 3 days', '2 weeks ago', or YYYY-MM-DD. "
                            "NEVER compute dates yourself."
                        ),
                    },
                    "date_range_end": {
                        "type": "string",
                        "description": (
                            "End of date range filter. Same format as "
                            "date_range_start. If omitted, defaults to same day "
                            "as date_range_start."
                        ),
                    },
                    "timezone": {
                        "type": "string",
                        "description": (
                            "User's timezone (e.g. 'America/New_York'). "
                            "Required for correct date resolution."
                        ),
                    },
                    "include_deleted": {
                        "type": "boolean",
                        "description": (
                            "Include canceled/deleted events in results. "
                            "Default false."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return. Default 20.",
                    },
                },
                "required": ["timezone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mutate_calendar_event",
            "description": (
                "Create, update, or delete a calendar event. "
                "ALWAYS use this tool — not read_calendar_events — when the user "
                "wants to move, change, reschedule, shift, update, mark, label, "
                "tag, categorize, set, or cancel an event. "
                "Mutation verbs (move, change, reschedule, shift, update, rename, "
                "mark, label, tag, set, cancel, delete, remove) MUST route here. "
                "For update/delete you can supply event_query+event_date instead of "
                "event_id and the system will resolve the event automatically. "
                "To change an event's category/domain (for color coding), use "
                "action='update' with event_type set to the new category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update", "delete"],
                        "description": (
                            "The mutation to perform. Use 'update' when the user says "
                            "move, change, reschedule, shift, update, rename, mark, "
                            "label, tag, categorize, set, or 'from X to Y'. "
                            "Use 'delete' when the user says cancel, remove, or delete."
                        ),
                    },
                    "idempotency_key": {
                        "type": "string",
                        "description": (
                            "Unique key to prevent duplicate mutations. "
                            "Generate a descriptive key like "
                            "'update-meeting-wed-to-thu-20260223'."
                        ),
                    },
                    "timezone": {
                        "type": "string",
                        "description": (
                            "User's timezone (e.g. 'America/New_York'). "
                            "Required for correct date/time handling."
                        ),
                    },
                    "event_id": {
                        "type": "integer",
                        "description": (
                            "ID of the event to update or delete. "
                            "If you don't know the ID, use event_query + "
                            "event_date instead and the system will find it."
                        ),
                    },
                    "event_query": {
                        "type": "string",
                        "description": (
                            "Title search text to find the event for update/delete. "
                            "Use when the user refers to an event by name, e.g. "
                            "'Workout', 'Bible Study', 'team meeting'. The system "
                            "performs a case-insensitive title match."
                        ),
                    },
                    "event_date": {
                        "type": "string",
                        "description": (
                            "Date hint to narrow event_query search for update/delete. "
                            "Pass weekday names with modifiers (e.g. 'next wednesday', "
                            "'wednesday', 'tomorrow') or YYYY-MM-DD. "
                            "NEVER compute dates yourself."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": (
                            "Event title. Required for create. For update, only "
                            "provide if renaming the event."
                        ),
                    },
                    "start_date": {
                        "type": "string",
                        "description": (
                            "New start date for the event. Pass weekday names "
                            "directly (e.g. 'monday', 'wednesday'). PRESERVE the "
                            "user's exact modifier: 'next wednesday' = following "
                            "week (not this week), 'last friday' = most recent past "
                            "Friday. Also accepts 'today', 'tomorrow', "
                            "'yesterday', 'in 3 days', or YYYY-MM-DD. "
                            "NEVER compute dates yourself. Required for create."
                        ),
                    },
                    "start_time": {
                        "type": "string",
                        "description": (
                            "New start time in HH:MM 24-hour format. "
                            "For update, this is the NEW time the user wants."
                        ),
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time (HH:MM format, 24-hour).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Event description or details.",
                    },
                    "event_type": {
                        "type": "string",
                        "enum": [
                            "personal", "family", "household", "faith",
                            "health", "work", "social", "travel", "other",
                        ],
                        "description": (
                            "Category/domain of the event (controls color coding). "
                            "For create: sets the initial domain. For update: changes "
                            "the domain. Use when the user says 'mark as faith', "
                            "'label as health', 'categorize as work', etc."
                        ),
                    },
                    "force_override": {
                        "type": "boolean",
                        "description": (
                            "Set to true ONLY when the user explicitly confirms "
                            "they want to override a calendar conflict. Never set "
                            "this on the first attempt — only after the system "
                            "reports a conflict and the user says 'override', "
                            "'proceed anyway', or 'book it anyway'."
                        ),
                    },
                },
                "required": ["action", "idempotency_key", "timezone"],
            },
        },
    },
]
