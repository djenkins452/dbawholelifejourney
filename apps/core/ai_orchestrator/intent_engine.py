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
    "log_sleep",
    "log_water",
    "log_steps",
    "log_body_measurement",
}

MEDICINE_INTENTS = {
    "take_medicine",
    "take_medicines_by_time",
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
    "create_routine_task",
    "complete_task",
    "read_task",
    "mutate_task",
    "create_event",
    "add_reminder",
    "read_calendar_events",
    "mutate_calendar_event",
}

FITNESS_INTENTS = {
    "log_workout",
    "log_exercise_set",
    "log_cardio",
}

TRANSFORMATION_INTENTS = {
    "log_transformation_protocol",
    "log_shopping_item",
    "complete_shopping_item",
}

SETTINGS_INTENTS = {
    "set_cos_name",
}

CALIBRATION_INTENTS = {
    "pause_calibration",
    "complete_calibration",
}

LEARNING_MODE_INTENTS = {
    "exit_learning_mode",
    "enter_learning_mode",
}

FINANCE_INTENTS = {
    "log_transaction",
    "check_budget",
}

SYSTEM_INTENTS = {
    "undo_last_action",
    "edit_last_entry",
}

# All intents that support a recorded_at timestamp override.
# IMPORTANT: If you add a new intent category, add it here too unless
# the intents truly have no date/time component. The test in
# test_intent_registration.py will FAIL if you forget.
TIME_AWARE_INTENTS = (
    HEALTH_INTENTS
    | MEDICINE_INTENTS
    | FASTING_INTENTS
    | JOURNAL_INTENTS
    | FAITH_INTENTS
    | FITNESS_INTENTS
    | TRANSFORMATION_INTENTS
    # Specific time-aware intents from other categories
    | {"log_habit", "complete_task", "log_transaction"}
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
    if intent_type in TRANSFORMATION_INTENTS:
        if intent_type == "log_transformation_protocol":
            return "health"
        elif intent_type in ("log_shopping_item", "complete_shopping_item"):
            return "life"
        else:
            return "health"
    if intent_type in SETTINGS_INTENTS:
        return "settings"
    if intent_type in CALIBRATION_INTENTS:
        return "core"
    if intent_type in LEARNING_MODE_INTENTS:
        return "core"
    if intent_type in FINANCE_INTENTS:
        return "finance"
    if intent_type in SYSTEM_INTENTS:
        return "core"
    return "unknown"


def is_time_aware(intent_type):
    """Check if an intent supports timestamp overrides."""
    return intent_type in TIME_AWARE_INTENTS


def is_context_aware(intent_type):
    """Check if an intent might reference contextual objects."""
    return intent_type in CONTEXT_AWARE_INTENTS
