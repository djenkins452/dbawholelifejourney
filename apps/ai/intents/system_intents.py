"""
System Intent Definitions

OpenAI function (tool) definitions for system-level actions:
- undo_last_action: Reverse the most recent data-logging action
- edit_last_entry: Edit the most recent entry for a data type
"""

SYSTEM_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "undo_last_action",
            "description": "Undo or reverse the last action taken by the assistant. Use when user says 'undo', 'undo that', 'that was wrong', 'delete that', 'remove that', 'take that back', or 'cancel that'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation": {
                        "type": "string",
                        "description": "What the user wants to undo. Optional — if empty, undoes the most recent action."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_last_entry",
            "description": "Edit or update the most recent entry for a data type. Use when user says 'change my weight to', 'update that to', 'actually it was', 'correct that', or 'fix that'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_type": {
                        "type": "string",
                        "enum": ["weight", "heart_rate", "blood_pressure", "glucose", "blood_oxygen", "sleep", "water", "steps", "journal", "food"],
                        "description": "Type of entry to edit. Infer from context or the last action."
                    },
                    "new_value": {
                        "type": "number",
                        "description": "New value to set (e.g., corrected weight, corrected heart rate)"
                    },
                    "field": {
                        "type": "string",
                        "description": "Specific field to update if not the primary value (e.g., 'notes', 'unit'). Optional."
                    },
                    "new_text": {
                        "type": "string",
                        "description": "New text value for text fields (e.g., updated notes or journal content). Optional."
                    }
                },
                "required": ["entry_type"]
            }
        }
    },
]
