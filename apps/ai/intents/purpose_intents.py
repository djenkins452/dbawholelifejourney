# ==============================================================================
# File: intents/purpose_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Purpose-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Purpose Intent Definitions

OpenAI function (tool) definitions for purpose-related actions:
- create_goal: Create a new life goal
- update_goal_progress: Log progress on an existing goal
- set_intention: Create a change intention
- log_habit: Log daily habit completion
"""

PURPOSE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_goal",
            "description": "Create a new life goal. Use when user wants to set a goal, aspiration, or something they want to achieve.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the goal"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the goal"
                    },
                    "why_it_matters": {
                        "type": "string",
                        "description": "Why this goal is important to the user"
                    },
                    "domain": {
                        "type": "string",
                        "enum": ["faith", "health", "family", "work", "finances", "learning", "personal_growth"],
                        "description": "Life domain this goal belongs to"
                    },
                    "timeframe": {
                        "type": "string",
                        "enum": ["within_1_year", "1-2_years", "2-3_years", "ongoing"],
                        "description": "Target timeframe for achieving the goal"
                    },
                    "target_date": {
                        "type": "string",
                        "description": "Specific target date if known (YYYY-MM-DD format)"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal_progress",
            "description": "Log progress on an existing goal. Use when user mentions progress, updates, or reflections on a goal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_keyword": {
                        "type": "string",
                        "description": "Keywords to identify which goal to update"
                    },
                    "progress_notes": {
                        "type": "string",
                        "description": "Notes about the progress made"
                    },
                    "mark_complete": {
                        "type": "boolean",
                        "description": "Whether to mark the goal as complete"
                    }
                },
                "required": ["goal_keyword", "progress_notes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_intention",
            "description": "Create an identity-based change intention. Use when user expresses who they want to become or a way of being they want to embody (e.g., 'I want to be more patient').",
            "parameters": {
                "type": "object",
                "properties": {
                    "intention": {
                        "type": "string",
                        "description": "The intention statement (e.g., 'Be more present', 'Lead with empathy')"
                    },
                    "description": {
                        "type": "string",
                        "description": "What this intention means to the user"
                    },
                    "motivation": {
                        "type": "string",
                        "description": "Why this intention matters"
                    }
                },
                "required": ["intention"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_habit",
            "description": "Log completion of a daily habit. Use when user mentions completing a habit or daily practice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "habit_keyword": {
                        "type": "string",
                        "description": "Keywords to identify which habit was completed"
                    },
                    "completed": {
                        "type": "boolean",
                        "description": "Whether the habit was completed (default true)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the habit completion"
                    }
                },
                "required": ["habit_keyword"]
            }
        }
    },
]
