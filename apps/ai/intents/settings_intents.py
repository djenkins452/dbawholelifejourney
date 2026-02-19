"""
Settings Intent Definitions

OpenAI function (tool) definitions for settings-related actions:
- set_cos_name: Change the Chief of Staff display name
"""

SETTINGS_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_cos_name",
            "description": (
                "Change the display name of the Chief of Staff / assistant. "
                "Use when the user says things like 'call yourself Max', "
                "'your name is now Friday', 'change your name to Jarvis', "
                "'I want to call you Sam', or 'rename yourself'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The new display name the user wants (e.g., 'Max', 'Friday', 'Jarvis'). Use empty string to reset to default."
                    }
                },
                "required": ["name"]
            }
        }
    },
]
