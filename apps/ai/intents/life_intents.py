# ==============================================================================
# File: intents/life_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Life-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Life Intent Definitions

OpenAI function (tool) definitions for life management actions:
- create_task: Create a new task
- create_routine_task: Create a daily routine task with CoS prompting
- complete_task: Mark a task as complete
- read_task: Query/lookup task details (time, due date, status)
- mutate_task: Reschedule, rename, or delete a task
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
                    },
                    "scheduled_time": {
                        "type": "string",
                        "description": "Specific time to do the task in HH:MM 24-hour format (e.g., '10:00', '14:30'). Use when the user specifies a time like 'at 10am', 'at 2:30pm'."
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Estimated duration in minutes (default 30). Used when scheduled_time is provided. Ignored if end_time is provided."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in HH:MM 24-hour format (e.g., '18:00'). Use when user specifies a time range like '5pm - 6pm' or '10:00 to 11:30'. If provided, duration is computed automatically from scheduled_time and end_time."
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_routine_task",
            "description": "Create a daily routine task with scheduled time and CoS check-ins. Use when user says 'add X to my daily routine', 'schedule workout every morning at 6am', 'I want a daily quiet time at 5:30am', or similar. These are recurring tasks with pre/post activity prompting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Routine task title (e.g., 'Quiet Time', 'Morning Workout', 'Evening Walk')"
                    },
                    "scheduled_time": {
                        "type": "string",
                        "description": "Begin time in HH:MM 24-hour format (e.g., '06:00', '17:30')"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in HH:MM 24-hour format (e.g., '06:30', '18:00'). If omitted, computed from duration_minutes."
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Estimated duration in minutes (default 30). Ignored if end_time is provided."
                    },
                    "recurrence_pattern": {
                        "type": "string",
                        "description": "How often: 'daily', 'weekdays', 'weekly:mon,wed,fri', etc. Default 'daily'."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes about the routine"
                    }
                },
                "required": ["title", "scheduled_time"]
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
            "name": "read_task",
            "description": "Look up task details. Use when user asks about a specific task's time, due date, status, or details. Examples: 'what time is my jeep task?', 'when is the grocery task due?', 'show me my tasks for today'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_keyword": {
                        "type": "string",
                        "description": "Keywords to search for in task titles (e.g., 'jeep', 'groceries', 'battery')"
                    },
                    "date_filter": {
                        "type": "string",
                        "description": "Filter by date: 'today', 'tomorrow', 'this_week', 'overdue', or YYYY-MM-DD"
                    },
                    "include_completed": {
                        "type": "boolean",
                        "description": "Include completed tasks in results (default false)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mutate_task",
            "description": (
                "Reschedule, rename, update, or delete a task. "
                "ALWAYS use this tool — not read_task — when the user "
                "wants to move, reschedule, push, postpone, rename, update, "
                "change, or delete a task. "
                "Mutation verbs (move, reschedule, push, postpone, change, "
                "rename, update, delete, remove) referring to tasks MUST route here. "
                "Use task_query to find the task by title keyword."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["update", "delete"],
                        "description": (
                            "The mutation to perform. Use 'update' when the user says "
                            "move, reschedule, push, postpone, change, rename, update. "
                            "Use 'delete' when the user says delete, remove, or cancel a task."
                        ),
                    },
                    "task_query": {
                        "type": "string",
                        "description": (
                            "Keywords to find the task by title (case-insensitive match). "
                            "E.g., 'office desk', 'groceries', 'battery'."
                        ),
                    },
                    "new_due_date": {
                        "type": "string",
                        "description": (
                            "New due date for the task. Pass the user's EXACT date phrase: "
                            "'today', 'tomorrow', 'monday', 'next friday', 'in 3 days', "
                            "or YYYY-MM-DD. NEVER compute dates yourself."
                        ),
                    },
                    "new_scheduled_time": {
                        "type": "string",
                        "description": "New scheduled time in HH:MM 24-hour format.",
                    },
                    "new_title": {
                        "type": "string",
                        "description": "New title if renaming the task.",
                    },
                    "new_notes": {
                        "type": "string",
                        "description": "New notes to replace or append to existing notes.",
                    },
                    "new_effort": {
                        "type": "string",
                        "enum": ["quick", "small", "medium", "large"],
                        "description": "New effort level.",
                    },
                    "new_end_time": {
                        "type": "string",
                        "description": "New end time in HH:MM 24-hour format.",
                    },
                    "apply_to_all": {
                        "type": "boolean",
                        "description": (
                            "When multiple tasks match (e.g., 'move those tasks to tomorrow'), "
                            "set to true to apply the change to ALL matching tasks. "
                            "Default false (single task only)."
                        ),
                    },
                    "delete_confirmed": {
                        "type": "boolean",
                        "description": (
                            "For delete actions ONLY. Set to true ONLY after the user has "
                            "explicitly confirmed they want to delete the task (e.g., 'yes', "
                            "'go ahead', 'confirm'). NEVER set this to true on the first call — "
                            "always let the system prompt the user for confirmation first."
                        ),
                    },
                },
                "required": ["action", "task_query"],
            },
        },
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
                        "description": "Event date. Pass weekday names directly (e.g. 'monday', 'wednesday', 'friday') — the server resolves them. PRESERVE the user's exact modifier: 'next wednesday' means the FOLLOWING week (not this week), 'last friday' means the most recent past Friday. Also accepts 'today', 'tomorrow', 'yesterday', 'in 3 days', '2 weeks from now', or YYYY-MM-DD. NEVER compute dates yourself — pass the natural language string."
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
                    },
                    "clone_from_last": {
                        "type": "boolean",
                        "description": "Set to true when user says 'same workout', 'same event', etc. Inherits title, time, duration, location, and type from the most recent scheduling action. Do NOT provide start_time when cloning unless the user explicitly states a new time."
                    },
                    "force_override": {
                        "type": "boolean",
                        "description": "Set to true ONLY when the user explicitly confirms they want to override a calendar conflict. Never set this on the first attempt — only after the system reports a conflict and the user says 'override', 'proceed anyway', or 'book it anyway'."
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
