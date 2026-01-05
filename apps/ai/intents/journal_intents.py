# ==============================================================================
# File: intents/journal_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Journal-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Journal Intent Definitions

OpenAI function (tool) definitions for journal-related actions:
- create_journal_entry: Create a new journal entry
- add_gratitude: Log gratitude (shorthand for gratitude journal)
"""

JOURNAL_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_journal_entry",
            "description": "Create a new journal entry for the user. Use when user wants to write, journal, reflect, or document their thoughts, experiences, or feelings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the journal entry. Generate a brief, meaningful title if not provided."
                    },
                    "body": {
                        "type": "string",
                        "description": "The main content of the journal entry - what the user wants to write about."
                    },
                    "mood": {
                        "type": "string",
                        "enum": ["great", "good", "okay", "down", "struggling"],
                        "description": "The user's current mood. Infer from content if not explicitly stated."
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Categories for the entry (e.g., 'gratitude', 'reflection', 'goals', 'prayer')"
                    }
                },
                "required": ["body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_gratitude",
            "description": "Log something the user is grateful for. Use when user expresses thankfulness or wants to record gratitude.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gratitude": {
                        "type": "string",
                        "description": "What the user is grateful for"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why they're grateful for this (optional context)"
                    }
                },
                "required": ["gratitude"]
            }
        }
    },
]
