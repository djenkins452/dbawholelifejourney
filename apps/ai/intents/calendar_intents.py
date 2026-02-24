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
                "Query the user's calendar to find events. Use BEFORE updating or "
                "deleting to resolve event references like 'my Wednesday event' or "
                "'the 2pm meeting' into specific event IDs. Also use when the user "
                "asks 'what's on my calendar' or 'do I have anything scheduled'."
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
                "Create, update, or delete a calendar event. Use 'update' to change "
                "event time, title, or details. Use 'delete' to cancel/remove an "
                "event. For update and delete, you MUST first call read_calendar_events "
                "to get the event_id. For create, this is an alternative to "
                "create_event — both work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update", "delete"],
                        "description": "The mutation to perform.",
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
                            "Required for update and delete actions. "
                            "Get this from read_calendar_events."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Event title. Required for create.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": (
                            "Event start date. Pass weekday names directly "
                            "(e.g. 'monday', 'wednesday'). PRESERVE the user's "
                            "exact modifier: 'next wednesday' = following week "
                            "(not this week), 'last friday' = most recent past "
                            "Friday. Also accepts 'today', 'tomorrow', "
                            "'yesterday', 'in 3 days', or YYYY-MM-DD. "
                            "NEVER compute dates yourself. Required for create."
                        ),
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time (HH:MM format, 24-hour).",
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
                        "description": "Type of event.",
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
