# ==============================================================================
# File: intents/medicine_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Medicine-related intent definitions for AI structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# ==============================================================================
"""
Medicine Intent Definitions

OpenAI function (tool) definitions for medicine-related actions:
- take_medicine: Log that user took a medicine
"""

MEDICINE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "take_medicine",
            "description": "Log that the user took a medicine. Use when user mentions taking, having, or using a medication.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medicine_name": {
                        "type": "string",
                        "description": "Name of the medicine (brand or generic name)"
                    },
                    "dose_label": {
                        "type": "string",
                        "description": "Optional dose label like 'morning', 'evening', 'bedtime' to identify which scheduled dose"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes about taking the medicine"
                    }
                },
                "required": ["medicine_name"]
            }
        }
    },
]
