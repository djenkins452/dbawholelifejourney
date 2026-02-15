"""
Intent Engine — Thin wrapper around the existing IntentService.

This does NOT replace the existing OpenAI-based intent detection.
It provides a unified interface for the orchestrator and adds
pre/post processing hooks for HTIE and SLCME enrichment.
"""

import logging

logger = logging.getLogger(__name__)


# Intent categories for routing
HEALTH_INTENTS = {
    "log_heart_rate",
    "log_blood_pressure",
    "log_weight",
    "log_glucose",
    "log_blood_oxygen",
    "log_food",
}

MEDICINE_INTENTS = {
    "take_medicine",
}

FASTING_INTENTS = {
    "start_fast",
    "end_fast",
}

JOURNAL_INTENTS = {
    "create_journal_entry",
    "add_gratitude",
}

FAITH_INTENTS = {
    "log_prayer",
    "mark_prayer_answered",
    "save_verse",
    "add_faith_milestone",
}

PURPOSE_INTENTS = {
    "create_goal",
    "update_goal_progress",
    "set_intention",
    "log_habit",
}

LIFE_INTENTS = {
    "create_task",
    "complete_task",
    "create_event",
    "add_reminder",
}

FITNESS_INTENTS = {
    "log_workout",
    "log_exercise_set",
    "log_cardio",
}

# All intents that support a recorded_at timestamp override
TIME_AWARE_INTENTS = (
    HEALTH_INTENTS
    | MEDICINE_INTENTS
    | FASTING_INTENTS
    | JOURNAL_INTENTS
    | FAITH_INTENTS
    | FITNESS_INTENTS
)

# All intents that might reference contextual objects
CONTEXT_AWARE_INTENTS = {
    "mark_prayer_answered",
    "save_verse",
    "update_goal_progress",
    "complete_task",
}


def get_intent_module(intent_type):
    """
    Map an intent type to its WLJ module name.

    Args:
        intent_type: The intent string (e.g., 'log_weight').

    Returns:
        Module name string (e.g., 'health', 'faith', 'purpose').
    """
    if intent_type in HEALTH_INTENTS:
        return "health"
    if intent_type in MEDICINE_INTENTS:
        return "health"
    if intent_type in FASTING_INTENTS:
        return "health"
    if intent_type in JOURNAL_INTENTS:
        return "journal"
    if intent_type in FAITH_INTENTS:
        return "faith"
    if intent_type in PURPOSE_INTENTS:
        return "purpose"
    if intent_type in LIFE_INTENTS:
        return "life"
    if intent_type in FITNESS_INTENTS:
        return "health"
    return "unknown"


def is_time_aware(intent_type):
    """Check if an intent supports timestamp overrides."""
    return intent_type in TIME_AWARE_INTENTS


def is_context_aware(intent_type):
    """Check if an intent might reference contextual objects."""
    return intent_type in CONTEXT_AWARE_INTENTS
