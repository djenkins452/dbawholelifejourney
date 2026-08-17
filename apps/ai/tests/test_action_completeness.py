# ==============================================================================
# File: apps/ai/tests/test_action_completeness.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proactive Phase 2 M4 — Action Completeness. Ratchets the SAFETY INVARIANT for
#   every action the certified CoS may perform: it must be Day-1-safe (in DAY1_ACTION_ALLOWLIST),
#   have a tool schema (ALL_INTENT_TOOLS) AND a handler (INTENT_HANDLERS), and therefore route
#   through the existing validate→confirm→execute→audit pipeline. Prevents a future unsafe
#   exposure (adding a name to ALLOWED_WRITE_INTENTS that skips the safe path).
# ==============================================================================
from django.test import TestCase


class ActionExposureSafetyInvariantTests(TestCase):
    def test_every_exposed_write_is_day1_safe_with_schema_and_handler(self):
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS
        from apps.ai.cos_services.action_execution import DAY1_ACTION_ALLOWLIST
        from apps.ai.intents import ALL_INTENT_TOOLS, INTENT_HANDLERS
        schema_names = {t["function"]["name"] for t in ALL_INTENT_TOOLS
                        if t.get("type") == "function"}
        for name in ALLOWED_WRITE_INTENTS:
            self.assertIn(name, DAY1_ACTION_ALLOWLIST,
                          f"{name} is exposed to the CoS but NOT Day-1-safe")
            self.assertIn(name, schema_names, f"{name} has no tool schema")
            self.assertIn(name, INTENT_HANDLERS, f"{name} has no handler")

    def test_high_leverage_actions_are_exposed(self):
        # The M4 coherent set — regression guard that we didn't lose the proactive-loop actions.
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS
        for name in ("create_event", "add_reminder", "log_workout", "log_habit",
                     "create_goal", "update_goal_progress", "log_prayer", "save_verse",
                     "create_journal_entry", "add_gratitude"):
            self.assertIn(name, ALLOWED_WRITE_INTENTS)

    def test_action_tools_all_build(self):
        # Every exposed write resolves to a real OpenAI tool def (no dangling name).
        from apps.ai.model_interface.constitution import action_tools, ALLOWED_WRITE_INTENTS
        built = {t["function"]["name"] for t in action_tools()}
        for name in ALLOWED_WRITE_INTENTS:
            self.assertIn(name, built)
