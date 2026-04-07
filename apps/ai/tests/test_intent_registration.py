# ==============================================================================
# File: test_intent_registration.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Validates that ALL intents are properly registered across
#              every engine/registry in the system. Catches registration gaps
#              BEFORE they ship.
#
# WHY THIS EXISTS:
#   Every new intent must be registered in 5+ places:
#     1. Tool definition (apps/ai/intents/*.py → ALL_INTENT_TOOLS)
#     2. Handler map (apps/ai/intents/__init__.py → INTENT_HANDLERS)
#     3. Intent engine category (apps/core/ai_orchestrator/intent_engine.py)
#     4. Execute dispatcher (apps/ai/intent_service.py → execute_intent)
#     5. Action handler method (apps/ai/action_handlers.py)
#
#   Without enforcement, every new feature is a manual multi-file registration
#   that gets forgotten. This test makes the build FAIL if any registration
#   is missing.
#
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-20
# ==============================================================================
"""
Intent Registration Completeness Tests

These tests ensure every intent in the WLJ AI system is properly registered
across all engines. If a test fails, it means someone added an intent in one
place but forgot to register it in another.

RUN: python manage.py test apps.ai.tests.test_intent_registration -v 2
"""

import inspect
import re

from django.test import TestCase

from apps.ai.intents import ALL_INTENT_TOOLS, INTENT_HANDLERS
from apps.ai.action_handlers import ActionHandler
from apps.core.ai_orchestrator.intent_engine import (
    HEALTH_INTENTS,
    INTAKE_INTENTS,
    FASTING_INTENTS,
    JOURNAL_INTENTS,
    FAITH_INTENTS,
    PURPOSE_INTENTS,
    LIFE_INTENTS,
    FITNESS_INTENTS,
    SETTINGS_INTENTS,
    CALIBRATION_INTENTS,
    TRANSFORMATION_INTENTS,
    LEARNING_MODE_INTENTS,
    EXPORT_INTENTS,
    FINANCE_INTENTS,
    SYSTEM_INTENTS,
    QUERY_INTENTS,
    TIME_AWARE_INTENTS,
    get_intent_module,
)


# ============================================================================
# Helpers
# ============================================================================

def _get_all_tool_names():
    """Extract all intent names from ALL_INTENT_TOOLS."""
    return [
        tool['function']['name']
        for tool in ALL_INTENT_TOOLS
        if 'function' in tool and 'name' in tool['function']
    ]


def _get_all_engine_intents():
    """Get the union of all intent category sets in intent_engine.py."""
    return (
        HEALTH_INTENTS
        | INTAKE_INTENTS
        | FASTING_INTENTS
        | JOURNAL_INTENTS
        | FAITH_INTENTS
        | PURPOSE_INTENTS
        | LIFE_INTENTS
        | FITNESS_INTENTS
        | SETTINGS_INTENTS
        | CALIBRATION_INTENTS
        | TRANSFORMATION_INTENTS
        | LEARNING_MODE_INTENTS
        | EXPORT_INTENTS
        | FINANCE_INTENTS
        | SYSTEM_INTENTS
        | QUERY_INTENTS
    )


def _get_handler_methods():
    """Get all handle_* method names on ActionHandler."""
    return {
        name for name in dir(ActionHandler)
        if name.startswith('handle_') and callable(getattr(ActionHandler, name))
    }


def _get_dispatch_intents():
    """
    Extract intent_type strings from the execute_intent if/elif chain.
    Reads source code to find all intent_type == 'xxx' patterns.
    """
    from apps.ai import intent_service as mod
    source = inspect.getsource(mod.IntentService.execute_intent)
    # Match patterns like: intent_type == 'log_heart_rate'
    return set(re.findall(r"intent_type\s*==\s*'(\w+)'", source))


# Intents that are NOT expected to have OpenAI tool definitions
# (they are handled internally, not triggered by user messages)
INTERNAL_ONLY_INTENTS = {
    # Transformation intents exist as handlers but may not yet have tool defs.
    # Remove from this set once tool definitions are created.
    'log_transformation_protocol',
    'log_shopping_item',
    'complete_shopping_item',
}

# Intents that don't need to be time-aware (no date/time component)
NON_TIME_INTENTS = {
    'pause_calibration',
    'complete_calibration',
    'set_cos_name',
    'enter_learning_mode',     # Control-plane — no date/time component
    'exit_learning_mode',      # Control-plane — no date/time component
    'complete_shopping_item',  # Updates existing item, no date
    'create_task',             # Tasks have due_date, not recorded_at
    'create_routine_task',     # Routine tasks have scheduled_time, not recorded_at
    'create_event',            # Events have start/end, not recorded_at
    'read_task',               # Read-only query, no recorded_at
    'read_calendar_events',    # Read-only query, no recorded_at
    'skip_task',               # Skips a task, no date/time component
    'mutate_task',             # Uses new_due_date/new_scheduled_time, not recorded_at
    'mutate_calendar_event',   # Uses start_date/start_time, not recorded_at
    'add_reminder',            # Reminders have a trigger time, not recorded_at
    'reschedule_routine_item', # Uses new_time for scheduling, not recorded_at
    'create_goal',             # Goals have target_date, not recorded_at
    'update_goal_progress',    # Progress updates, not backdatable
    'set_intention',           # Intentions are forward-looking
    'undo_last_action',        # Undoes last action, no date component
    'edit_last_entry',         # Edits most recent, no date component
    'check_budget',            # Read-only query
    'email_intake_list',       # Sends email, no date/time component
    'generate_report',         # Generates report, no recorded_at
    'query_event_history',     # Read-only event query, no recorded_at
}


# ============================================================================
# Tests
# ============================================================================

class IntentRegistrationTest(TestCase):
    """
    Validates that every intent is registered in all required places.
    If any test fails, a registration gap exists that must be fixed.
    """

    def test_every_tool_has_handler_mapping(self):
        """Every tool in ALL_INTENT_TOOLS must have an INTENT_HANDLERS entry."""
        tool_names = _get_all_tool_names()
        missing = [name for name in tool_names if name not in INTENT_HANDLERS]
        self.assertEqual(
            missing, [],
            f"These intents have tool definitions but NO INTENT_HANDLERS entry: {missing}\n"
            f"Fix: Add them to INTENT_HANDLERS in apps/ai/intents/__init__.py"
        )

    def test_every_tool_has_engine_category(self):
        """Every tool in ALL_INTENT_TOOLS must exist in an intent_engine category."""
        tool_names = _get_all_tool_names()
        all_engine = _get_all_engine_intents()
        missing = [name for name in tool_names if name not in all_engine]
        self.assertEqual(
            missing, [],
            f"These intents have tool definitions but NO intent_engine category: {missing}\n"
            f"Fix: Add them to the appropriate set in "
            f"apps/core/ai_orchestrator/intent_engine.py"
        )

    def test_every_tool_has_dispatch_case(self):
        """Every tool in ALL_INTENT_TOOLS must have a case in execute_intent()."""
        tool_names = _get_all_tool_names()
        dispatched = _get_dispatch_intents()
        missing = [name for name in tool_names if name not in dispatched]
        self.assertEqual(
            missing, [],
            f"These intents have tool definitions but NO execute_intent() case: {missing}\n"
            f"Fix: Add an elif branch in IntentService.execute_intent() in "
            f"apps/ai/intent_service.py"
        )

    def test_every_tool_has_handler_method(self):
        """Every tool in ALL_INTENT_TOOLS must have a handle_<name> method."""
        tool_names = _get_all_tool_names()
        methods = _get_handler_methods()
        missing = [
            name for name in tool_names
            if f"handle_{name}" not in methods
        ]
        self.assertEqual(
            missing, [],
            f"These intents have tool definitions but NO handler method: {missing}\n"
            f"Fix: Add handle_<name> methods to ActionHandler in "
            f"apps/ai/action_handlers.py"
        )

    def test_every_handler_mapping_has_tool(self):
        """Every INTENT_HANDLERS entry must have a corresponding tool definition."""
        tool_names = set(_get_all_tool_names())
        missing = [
            name for name in INTENT_HANDLERS
            if name != 'no_action'
            and name not in tool_names
            and name not in INTERNAL_ONLY_INTENTS
        ]
        self.assertEqual(
            missing, [],
            f"These intents have INTENT_HANDLERS entries but NO tool definition: {missing}\n"
            f"Fix: Either create tool definitions in apps/ai/intents/ or remove "
            f"the INTENT_HANDLERS entry"
        )

    def test_every_dispatch_case_has_tool(self):
        """Every execute_intent() case should have a corresponding tool."""
        tool_names = set(_get_all_tool_names())
        dispatched = _get_dispatch_intents()
        missing = [
            name for name in dispatched
            if name not in tool_names
            and name not in INTERNAL_ONLY_INTENTS
        ]
        self.assertEqual(
            missing, [],
            f"These intents have execute_intent() cases but NO tool definition: {missing}\n"
            f"Fix: Either create tool definitions or the dispatch case is dead code"
        )

    def test_engine_categories_cover_all_tools(self):
        """The union of all engine category sets must cover every tool."""
        tool_names = set(_get_all_tool_names())
        all_engine = _get_all_engine_intents()
        not_in_engine = tool_names - all_engine
        self.assertEqual(
            not_in_engine, set(),
            f"These intents are NOT in any engine category: {not_in_engine}\n"
            f"Fix: Add them to the appropriate set in intent_engine.py"
        )

    def test_time_aware_covers_date_intents(self):
        """
        All intents that deal with dates/times should be in TIME_AWARE_INTENTS.
        Only explicitly excluded intents (NON_TIME_INTENTS) are allowed to be missing.
        """
        all_engine = _get_all_engine_intents()
        not_time_aware = all_engine - TIME_AWARE_INTENTS - NON_TIME_INTENTS
        self.assertEqual(
            not_time_aware, set(),
            f"These intents are NOT in TIME_AWARE_INTENTS and NOT in "
            f"NON_TIME_INTENTS: {not_time_aware}\n"
            f"Fix: Either add them to TIME_AWARE_INTENTS in intent_engine.py "
            f"or add them to NON_TIME_INTENTS in this test if they truly "
            f"don't need time awareness"
        )

    def test_get_intent_module_returns_known_module(self):
        """Every engine-registered intent must map to a known module, not 'unknown'."""
        all_engine = _get_all_engine_intents()
        unknown = [
            intent for intent in all_engine
            if get_intent_module(intent) == 'unknown'
        ]
        self.assertEqual(
            unknown, [],
            f"These intents return 'unknown' from get_intent_module(): {unknown}\n"
            f"Fix: Add a mapping in get_intent_module() in intent_engine.py"
        )

    def test_all_intents_have_action_policy(self):
        """
        Every intent in INTENT_HANDLERS must be explicitly registered in
        ACTION_POLICY. The safe default catches unregistered intents at
        runtime, but explicit registration ensures correct risk level,
        category, and authority for every intent.

        This is the governance line: no new mutation tool ships without
        explicit ACTION_POLICY registration.
        """
        from apps.core.ai_orchestrator.action_policy import ACTION_POLICY
        all_intents = set(INTENT_HANDLERS.keys()) - {'no_action'}
        registered = set(ACTION_POLICY.keys())
        missing = all_intents - registered
        self.assertFalse(
            missing,
            f"Intents missing from ACTION_POLICY ({len(missing)}): "
            f"{sorted(missing)}. "
            f"Fix: Add _r() entries in "
            f"apps/core/ai_orchestrator/action_policy.py for each."
        )

    def test_no_orphaned_handler_methods(self):
        """
        Every handle_* method on ActionHandler should correspond to a known intent.
        Catches leftover methods from deleted intents.
        """
        methods = _get_handler_methods()
        dispatched = _get_dispatch_intents()
        # Convert dispatch intents to handler names
        expected_methods = {f"handle_{name}" for name in dispatched}
        # Also include internal helpers that start with handle_ but aren't intents
        internal_helpers = {
            'handle_proactive_response',
        }
        orphaned = methods - expected_methods - internal_helpers
        # Don't fail on orphaned — just warn. Some may be legitimate.
        # This is informational, not a hard gate.
        if orphaned:
            import warnings
            warnings.warn(
                f"Potentially orphaned handler methods (no dispatch case): "
                f"{orphaned}"
            )
