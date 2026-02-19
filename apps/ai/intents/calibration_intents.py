# ==============================================================================
# File: intents/calibration_intents.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Calibration intent definitions for pausing/resuming onboarding
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-19
# ==============================================================================
"""
Calibration Intent Definitions

OpenAI function (tool) definitions for calibration-related actions:
- pause_calibration: Pause the getting-to-know-you questions
"""

CALIBRATION_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "pause_calibration",
            "description": (
                "Pause the getting-to-know-you / onboarding questions. "
                "Use when the user says things like 'pause', 'enough for now', "
                "'stop asking', 'that's enough', 'continue later', 'ask me later', "
                "'stop for now', 'let's take a break', 'no more questions', "
                "'I'm done for now', 'enough questions', 'let's do more later', "
                "'pick this up later'. Do NOT use for normal conversation pauses "
                "or topic changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
