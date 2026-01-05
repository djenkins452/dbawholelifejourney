# ==============================================================================
# File: intents/fasting_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fasting-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Fasting Intent Definitions

OpenAI function (tool) definitions for fasting-related actions:
- start_fast: Begin a new fasting window
- end_fast: End the current fasting window
"""

FASTING_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_fast",
            "description": "Start a new fasting window for the user. Use when user mentions starting, beginning, or entering a fast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fasting_type": {
                        "type": "string",
                        "enum": ["16:8", "18:6", "20:4", "OMAD", "24h", "36h", "custom"],
                        "description": "Type of fast. Default to '16:8' if not specified."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any notes about starting the fast"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "end_fast",
            "description": "End the user's current fasting window. Use when user mentions ending, breaking, or finishing their fast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "notes": {
                        "type": "string",
                        "description": "Any notes about ending the fast"
                    }
                },
                "required": []
            }
        }
    },
]
