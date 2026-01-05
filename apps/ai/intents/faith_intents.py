# ==============================================================================
# File: intents/faith_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Faith-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Faith Intent Definitions

OpenAI function (tool) definitions for faith-related actions:
- log_prayer: Create a new prayer request
- mark_prayer_answered: Mark a prayer as answered
- save_verse: Save a scripture verse
- add_faith_milestone: Record a spiritual milestone
"""

FAITH_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_prayer",
            "description": "Create a new prayer request. Use when user mentions praying for someone/something or wants to add a prayer to track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Brief title for the prayer request"
                    },
                    "description": {
                        "type": "string",
                        "description": "Details about the prayer request"
                    },
                    "person_or_situation": {
                        "type": "string",
                        "description": "Who or what the prayer is for"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["urgent", "high", "normal", "ongoing"],
                        "description": "Priority level. Default to 'normal' unless user indicates urgency."
                    },
                    "is_personal": {
                        "type": "boolean",
                        "description": "Whether this is a personal prayer (true) or for others (false)"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mark_prayer_answered",
            "description": "Mark a prayer request as answered. Use when user says a prayer was answered or God answered their prayer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prayer_keyword": {
                        "type": "string",
                        "description": "Keywords to identify which prayer was answered (will search active prayers)"
                    },
                    "answer_notes": {
                        "type": "string",
                        "description": "How the prayer was answered - the testimony"
                    }
                },
                "required": ["prayer_keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_verse",
            "description": "Save a scripture verse to the user's collection. Use when user wants to save, bookmark, or remember a Bible verse.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Scripture reference (e.g., 'John 3:16', 'Psalm 23:1-3')"
                    },
                    "text": {
                        "type": "string",
                        "description": "The verse text if provided by user"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Personal notes about why this verse is meaningful"
                    },
                    "is_memory_verse": {
                        "type": "boolean",
                        "description": "Whether user wants to memorize this verse"
                    },
                    "themes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Themes or topics the verse relates to (e.g., 'faith', 'hope', 'love')"
                    }
                },
                "required": ["reference"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_faith_milestone",
            "description": "Record a spiritual milestone or significant faith moment. Use when user mentions a spiritual experience, answered prayer testimony, or faith journey moment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the milestone"
                    },
                    "milestone_type": {
                        "type": "string",
                        "enum": ["salvation", "baptism", "rededication", "answered_prayer", "spiritual_insight", "community", "other"],
                        "description": "Type of milestone"
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the milestone and what it means"
                    },
                    "scripture_reference": {
                        "type": "string",
                        "description": "Related scripture reference if any"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the milestone (YYYY-MM-DD format)"
                    }
                },
                "required": ["title", "milestone_type"]
            }
        }
    },
]
