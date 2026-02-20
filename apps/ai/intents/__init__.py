# ==============================================================================
# File: intents/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Intent definitions for AI Assistant structured data extraction
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# Updated: 2026-01-04 - Added Phase 2 intents (Journal, Faith, Purpose, Life, Fitness)
# ==============================================================================
"""
Intent Definitions for AI Assistant

This package contains OpenAI function (tool) definitions for intent recognition.
Each intent defines a structured action the user can take through natural language.

Supported Intent Categories:
- Health: log_heart_rate, log_blood_pressure, log_weight, log_glucose, log_blood_oxygen, log_food
- Medicine: take_medicine
- Fasting: start_fast, end_fast
- Journal: create_journal_entry, add_gratitude
- Faith: log_prayer, mark_prayer_answered, save_verse, add_faith_milestone
- Purpose: create_goal, update_goal_progress, set_intention, log_habit
- Life: create_task, complete_task, create_event, add_reminder
- Fitness: log_workout, log_exercise_set, log_cardio
"""

from .health_intents import HEALTH_INTENT_TOOLS
from .medicine_intents import MEDICINE_INTENT_TOOLS
from .fasting_intents import FASTING_INTENT_TOOLS
from .journal_intents import JOURNAL_INTENT_TOOLS
from .faith_intents import FAITH_INTENT_TOOLS
from .purpose_intents import PURPOSE_INTENT_TOOLS
from .life_intents import LIFE_INTENT_TOOLS
from .fitness_intents import FITNESS_INTENT_TOOLS
from .settings_intents import SETTINGS_INTENT_TOOLS
from .calibration_intents import CALIBRATION_INTENT_TOOLS

# Combine all intent tools for the OpenAI API
ALL_INTENT_TOOLS = (
    HEALTH_INTENT_TOOLS +
    MEDICINE_INTENT_TOOLS +
    FASTING_INTENT_TOOLS +
    JOURNAL_INTENT_TOOLS +
    FAITH_INTENT_TOOLS +
    PURPOSE_INTENT_TOOLS +
    LIFE_INTENT_TOOLS +
    FITNESS_INTENT_TOOLS +
    SETTINGS_INTENT_TOOLS +
    CALIBRATION_INTENT_TOOLS
)

# Intent type to handler mapping (for routing)
INTENT_HANDLERS = {
    # Health
    'log_heart_rate': 'health',
    'log_blood_pressure': 'health',
    'log_weight': 'health',
    'log_glucose': 'health',
    'log_blood_oxygen': 'health',
    'log_food': 'health',
    # Medicine
    'take_medicine': 'medicine',
    # Fasting
    'start_fast': 'fasting',
    'end_fast': 'fasting',
    # Journal
    'create_journal_entry': 'journal',
    'add_gratitude': 'journal',
    # Faith
    'log_prayer': 'faith',
    'mark_prayer_answered': 'faith',
    'save_verse': 'faith',
    'add_faith_milestone': 'faith',
    # Purpose
    'create_goal': 'purpose',
    'update_goal_progress': 'purpose',
    'set_intention': 'purpose',
    'log_habit': 'purpose',
    # Life
    'create_task': 'life',
    'complete_task': 'life',
    'create_event': 'life',
    'add_reminder': 'life',
    # Fitness
    'log_workout': 'fitness',
    'log_exercise_set': 'fitness',
    'log_cardio': 'fitness',
    # Settings
    'set_cos_name': 'settings',
    # Calibration
    'pause_calibration': 'calibration',
    'complete_calibration': 'calibration',
    # Transformation
    'log_transformation_protocol': 'transformation',
    'log_shopping_item': 'transformation',
    'complete_shopping_item': 'transformation',
    # No action
    'no_action': None,
}

__all__ = [
    'ALL_INTENT_TOOLS',
    'INTENT_HANDLERS',
    'HEALTH_INTENT_TOOLS',
    'MEDICINE_INTENT_TOOLS',
    'FASTING_INTENT_TOOLS',
    'JOURNAL_INTENT_TOOLS',
    'FAITH_INTENT_TOOLS',
    'PURPOSE_INTENT_TOOLS',
    'LIFE_INTENT_TOOLS',
    'FITNESS_INTENT_TOOLS',
    'SETTINGS_INTENT_TOOLS',
    'CALIBRATION_INTENT_TOOLS',
]
