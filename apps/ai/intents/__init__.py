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
- Health: log_heart_rate, log_blood_pressure, log_weight, log_glucose, log_blood_oxygen,
          log_food, log_sleep, log_water, log_steps, log_body_measurement
- Medicine: take_medicine, take_medicines_by_time, email_medicine_list
- Fasting: start_fast, end_fast
- Journal: create_journal_entry, add_gratitude
- Faith: log_prayer, mark_prayer_answered, save_verse, add_faith_milestone
- Purpose: create_goal, update_goal_progress, set_intention, log_habit
- Life: create_task, create_routine_task, complete_task, skip_task, mutate_task, create_event, add_reminder
- Fitness: log_workout, log_exercise_set, log_cardio
- Finance: log_transaction, check_budget
- System: undo_last_action, edit_last_entry
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
from .learning_mode_intents import LEARNING_MODE_INTENT_TOOLS
from .calendar_intents import CALENDAR_INTENT_TOOLS
from .finance_intents import FINANCE_INTENT_TOOLS
from .system_intents import SYSTEM_INTENT_TOOLS
from .query_intents import QUERY_INTENT_TOOLS

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
    CALIBRATION_INTENT_TOOLS +
    LEARNING_MODE_INTENT_TOOLS +
    CALENDAR_INTENT_TOOLS +
    FINANCE_INTENT_TOOLS +
    SYSTEM_INTENT_TOOLS +
    QUERY_INTENT_TOOLS
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
    'log_sleep': 'health',
    'log_water': 'health',
    'log_steps': 'health',
    'log_body_measurement': 'health',
    # Medicine
    'take_medicine': 'medicine',
    'take_medicines_by_time': 'medicine',
    'email_medicine_list': 'medicine',
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
    'create_routine_task': 'life',
    'complete_task': 'life',
    'skip_task': 'life',
    'read_task': 'life',
    'mutate_task': 'life',
    'create_event': 'life',
    'add_reminder': 'life',
    'reschedule_routine_item': 'life',
    # Calendar CRUD
    'read_calendar_events': 'life',
    'mutate_calendar_event': 'life',
    # Fitness
    'log_workout': 'fitness',
    'log_exercise_set': 'fitness',
    'log_cardio': 'fitness',
    # Settings
    'set_cos_name': 'settings',
    # Calibration
    'pause_calibration': 'calibration',
    'complete_calibration': 'calibration',
    # Learning Mode (control-plane — bypasses UAIO suppression)
    'exit_learning_mode': 'learning_mode',
    'enter_learning_mode': 'learning_mode',
    # Transformation
    'log_transformation_protocol': 'transformation',
    'log_shopping_item': 'transformation',
    'complete_shopping_item': 'transformation',
    # Finance
    'log_transaction': 'finance',
    'check_budget': 'finance',
    # System (undo/edit)
    'undo_last_action': 'system',
    'edit_last_entry': 'system',
    # Cross-domain event queries (read-only)
    'query_event_history': 'query',
    # No action
    'no_action': None,
}

# =============================================================================
# Domain-Scoped Tool Sets (Phase 5 Token Governance)
# =============================================================================
# Maps router domain → only the relevant tool schemas. Reduces ~19K tokens
# to ~2-6K when the domain is known. Unknown/None domain → ALL tools.

# Tools always included regardless of domain (cross-cutting).
# NOTE: SETTINGS_INTENT_TOOLS intentionally EXCLUDED from core tools.
# set_cos_name was causing cross-domain misrouting — e.g., "move workout"
# triggering "rename assistant". Settings intents only load when the
# router detects an explicit settings domain or domain is unknown.
CORE_INTENT_TOOLS = (
    SYSTEM_INTENT_TOOLS +
    CALIBRATION_INTENT_TOOLS +
    LEARNING_MODE_INTENT_TOOLS +
    QUERY_INTENT_TOOLS  # Cross-domain event queries available in all scopes
)

DOMAIN_INTENT_TOOLS = {
    'health': (
        HEALTH_INTENT_TOOLS + MEDICINE_INTENT_TOOLS +
        FASTING_INTENT_TOOLS + FITNESS_INTENT_TOOLS +
        # Include LIFE tools for health domain because routine items
        # (workout, prayer) cross health/life boundaries. Without this,
        # "move my workout to 7pm" has no matching intent in health scope.
        LIFE_INTENT_TOOLS
    ),
    'faith': FAITH_INTENT_TOOLS,
    'journal': JOURNAL_INTENT_TOOLS,
    'goals': PURPOSE_INTENT_TOOLS,
    'tasks': LIFE_INTENT_TOOLS + CALENDAR_INTENT_TOOLS,
    'finance': FINANCE_INTENT_TOOLS,
    'settings': SETTINGS_INTENT_TOOLS,
}


def get_scoped_intent_tools(domain=None):
    """
    Get domain-scoped intent tool schemas for OpenAI function calling.

    When WLJ_SCOPED_INTENT_TOOLS_ENABLED is True and domain is known,
    returns only the domain-relevant tools + core tools, reducing token
    count from ~19K to ~2-6K.

    Args:
        domain: str or None from router's inferred domain.

    Returns:
        List of OpenAI tool schema dicts.
    """
    from django.conf import settings as _s
    if not getattr(_s, 'WLJ_SCOPED_INTENT_TOOLS_ENABLED', False):
        return ALL_INTENT_TOOLS
    if domain is None:
        return ALL_INTENT_TOOLS
    domain_tools = DOMAIN_INTENT_TOOLS.get(domain)
    if domain_tools is None:
        return ALL_INTENT_TOOLS
    return list(domain_tools) + list(CORE_INTENT_TOOLS)


__all__ = [
    'ALL_INTENT_TOOLS',
    'INTENT_HANDLERS',
    'CORE_INTENT_TOOLS',
    'DOMAIN_INTENT_TOOLS',
    'get_scoped_intent_tools',
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
    'LEARNING_MODE_INTENT_TOOLS',
    'CALENDAR_INTENT_TOOLS',
    'FINANCE_INTENT_TOOLS',
    'SYSTEM_INTENT_TOOLS',
    'QUERY_INTENT_TOOLS',
]
