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
- complete_calibration: Finish the intro — user says they're ready
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
    {
        "type": "function",
        "function": {
            "name": "complete_calibration",
            "description": (
                "Finish the getting-to-know-you introduction. The user is "
                "saying they're ready for you to start working as their CoS. "
                "Use when the user says things like 'I think you know me well "
                "enough', 'finish the intro', 'I'm ready', 'let's get to work', "
                "'you know enough about me', 'that's everything', 'done with "
                "introductions', 'wrap up the intro', 'introduction complete', "
                "'start being my CoS'. Do NOT use this for pausing — only when "
                "they explicitly want to FINISH introductions permanently."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
