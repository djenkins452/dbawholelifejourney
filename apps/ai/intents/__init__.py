# ==============================================================================
# File: intents/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Intent definitions for AI Assistant structured data extraction
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# ==============================================================================
"""
Intent Definitions for AI Assistant

This package contains OpenAI function (tool) definitions for intent recognition.
Each intent defines a structured action the user can take through natural language.

Supported Intent Categories:
- Health: log_heart_rate, log_blood_pressure, log_weight, log_glucose, log_blood_oxygen, log_food
- Medicine: take_medicine
- Fasting: start_fast, end_fast
"""

from .health_intents import HEALTH_INTENT_TOOLS
from .medicine_intents import MEDICINE_INTENT_TOOLS
from .fasting_intents import FASTING_INTENT_TOOLS

# Combine all intent tools for the OpenAI API
ALL_INTENT_TOOLS = (
    HEALTH_INTENT_TOOLS +
    MEDICINE_INTENT_TOOLS +
    FASTING_INTENT_TOOLS
)

# Intent type to handler mapping (for routing)
INTENT_HANDLERS = {
    'log_heart_rate': 'health',
    'log_blood_pressure': 'health',
    'log_weight': 'health',
    'log_glucose': 'health',
    'log_blood_oxygen': 'health',
    'log_food': 'health',
    'take_medicine': 'medicine',
    'start_fast': 'fasting',
    'end_fast': 'fasting',
    'no_action': None,
}

__all__ = [
    'ALL_INTENT_TOOLS',
    'INTENT_HANDLERS',
    'HEALTH_INTENT_TOOLS',
    'MEDICINE_INTENT_TOOLS',
    'FASTING_INTENT_TOOLS',
]
