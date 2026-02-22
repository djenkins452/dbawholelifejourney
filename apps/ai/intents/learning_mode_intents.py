# ==============================================================================
# File: intents/learning_mode_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Learning Mode control-plane intent definitions
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-22
# ==============================================================================
"""
Learning Mode Intent Definitions

OpenAI function (tool) definitions for Learning Mode state transitions:
- exit_learning_mode: Exit Learning Mode and resume execution
- enter_learning_mode: Enter Learning Mode to listen without executing

These are control-plane operations that bypass UAIO execution suppression.
"""

LEARNING_MODE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "exit_learning_mode",
            "description": (
                "Exit Learning Mode and resume normal execution. Use when the "
                "user says things like 'exit learning mode', 'done learning', "
                "'stop learning', 'I'm ready', 'let's get started', "
                "'ready to start', 'start executing', 'you can take actions now', "
                "'done teaching you', 'finish learning', 'resume actions', "
                "'stop listening mode', 'start doing things'. "
                "Do NOT use for general conversation or topic changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enter_learning_mode",
            "description": (
                "Enter Learning Mode — pause all execution and just listen. "
                "Use when the user says things like 'enter learning mode', "
                "'just listen', 'don't execute anything', 'learning mode', "
                "'stop taking actions', 'just learn for now', "
                "'listen only', 'pause execution', 'I want to teach you'. "
                "Do NOT use for general conversation or topic changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
