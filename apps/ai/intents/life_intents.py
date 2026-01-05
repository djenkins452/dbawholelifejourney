# ==============================================================================
# File: intents/life_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Life-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Life Intent Definitions

OpenAI function (tool) definitions for life management actions:
- create_task: Create a new task
- complete_task: Mark a task as complete
- create_event: Schedule a calendar event
- add_reminder: Create a reminder for a significant event (birthday, anniversary)
"""

LIFE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task. Use when user wants to add something to their to-do list or needs to remember to do something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title or description of the task"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional details or notes about the task"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "When the task is due (YYYY-MM-DD format or relative like 'tomorrow', 'next week')"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["now", "soon", "someday"],
                        "description": "Priority level. 'now' for urgent, 'soon' for this week, 'someday' for backlog."
                    },
                    "effort": {
                        "type": "string",
                        "enum": ["quick", "small", "medium", "large"],
                        "description": "Estimated effort. 'quick' (<5 min), 'small' (<30 min), 'medium' (1-2 hrs), 'large' (half day+)."
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of project to associate with (optional)"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as complete. Use when user says they finished, completed, or done with a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_keyword": {
                        "type": "string",
                        "description": "Keywords to identify which task was completed"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional completion notes"
                    }
                },
                "required": ["task_keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Schedule a calendar event. Use when user wants to add something to their calendar or schedule an appointment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the event"
                    },
                    "description": {
                        "type": "string",
                        "description": "Description or details about the event"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Event date (YYYY-MM-DD format)"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time (HH:MM format, 24-hour)"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time (HH:MM format, 24-hour)"
                    },
                    "is_all_day": {
                        "type": "boolean",
                        "description": "Whether this is an all-day event"
                    },
                    "location": {
                        "type": "string",
                        "description": "Location of the event"
                    },
                    "event_type": {
                        "type": "string",
                        "enum": ["personal", "family", "household", "faith", "health", "work", "social", "travel", "other"],
                        "description": "Type of event"
                    },
                    "reminder_minutes": {
                        "type": "integer",
                        "description": "Minutes before event to send reminder (e.g., 15, 30, 60)"
                    }
                },
                "required": ["title", "start_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Add a significant event reminder (birthday, anniversary, memorial). Use when user wants to remember an important date for a person.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title (e.g., 'John's Birthday', 'Wedding Anniversary')"
                    },
                    "event_type": {
                        "type": "string",
                        "enum": ["birthday", "anniversary", "memorial", "milestone", "holiday", "other"],
                        "description": "Type of significant event"
                    },
                    "person_name": {
                        "type": "string",
                        "description": "Name of the person this event is for"
                    },
                    "event_date": {
                        "type": "string",
                        "description": "Date of the event (MM-DD format for recurring, or YYYY-MM-DD for one-time)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Additional notes about this event"
                    },
                    "reminder_days": {
                        "type": "integer",
                        "description": "Days before to receive reminder (default 7)"
                    }
                },
                "required": ["title", "event_type", "event_date"]
            }
        }
    },
]
