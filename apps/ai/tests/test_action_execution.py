# ==============================================================================
# File: apps/ai/tests/test_action_execution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the ChatGPT CoS ActionExecutionService (Phase 6)
# ==============================================================================
"""
Phase 6 — execute_action tests.

Verifies the single write surface:
* allowlist gate (disallowed -> denied, no execution);
* confirmation gate reusing ACTION_POLICY (high-risk/destructive -> confirmation_required);
* routes through IntentService.execute_intent (single path, no new write path);
* maps ActionResult -> JSON-safe envelope; never raises; observable.
"""

import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services import allowed_actions, execute_action

User = get_user_model()

_EXEC = "apps.ai.intent_service.IntentService.execute_intent"


def _action_result(success=True, message="done", created_object=None, error=None):
    return SimpleNamespace(success=success, message=message,
                           created_object=created_object, error=error,
                           action_type=None, confirmation_detail=None)


class ActionExecutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cos_act@example.com", password="x")

    # --- allowlist --------------------------------------------------------
    def test_disallowed_action_denied_without_executing(self):
        with mock.patch(_EXEC) as ex:
            env = execute_action(self.user, "delete_account", {})
        self.assertEqual(env["status"], "denied")
        self.assertEqual(env["code"], "not_allowlisted")
        ex.assert_not_called()
        self.assertIn("allowed_actions", env)

    def test_allowlist_contents(self):
        a = allowed_actions()
        for must in ("create_task", "complete_task", "create_journal_entry",
                     "log_prayer", "create_event", "log_habit"):
            self.assertIn(must, a)
        # destructive actions are NOT in the allowlist
        self.assertNotIn("delete_task", a)

    # --- confirmation gate (reuses ACTION_POLICY) ------------------------
    def test_routine_action_executes_without_confirmation(self):
        # log_prayer is LOG/LOW -> no confirmation needed
        with mock.patch(_EXEC, return_value=_action_result(message="Prayer logged.")) as ex:
            env = execute_action(self.user, "log_prayer", {"title": "Health"})
        self.assertEqual(env["status"], "success")
        self.assertEqual(env["message"], "Prayer logged.")
        ex.assert_called_once()

    def test_high_risk_action_requires_confirmation(self):
        # mutate_task is MUTATE/HIGH -> confirmation required
        with mock.patch(_EXEC) as ex:
            env = execute_action(self.user, "mutate_task", {"task_keyword": "x"})
        self.assertEqual(env["status"], "confirmation_required")
        ex.assert_not_called()

    def test_confirmed_true_allows_high_risk_action(self):
        with mock.patch(_EXEC, return_value=_action_result(message="Task updated.")) as ex:
            env = execute_action(self.user, "mutate_task",
                                 {"task_keyword": "x", "confirmed": True})
        self.assertEqual(env["status"], "success")
        ex.assert_called_once()
        # the control flag is stripped before reaching the handler
        intent_arg = ex.call_args.args[0]
        self.assertNotIn("confirmed", intent_arg.parameters)

    # --- single path: builds IntentResult, calls execute_intent ----------
    def test_routes_through_execute_intent_with_intent_result(self):
        with mock.patch(_EXEC, return_value=_action_result(
                created_object={"id": 5, "title": "Buy milk"})) as ex:
            env = execute_action(self.user, "create_task", {"title": "Buy milk"})
        self.assertEqual(env["status"], "success")
        self.assertEqual(env["result"], {"id": 5, "title": "Buy milk"})
        intent_arg = ex.call_args.args[0]
        self.assertEqual(intent_arg.intent_type, "create_task")
        self.assertEqual(intent_arg.parameters, {"title": "Buy milk"})

    # --- failure / safety semantics --------------------------------------
    def test_handler_failure_maps_to_failed(self):
        with mock.patch(_EXEC, return_value=_action_result(
                success=False, message="Task not found.", error="not_found")):
            env = execute_action(self.user, "complete_task", {"task_keyword": "zzz"})
        self.assertEqual(env["status"], "failed")
        self.assertEqual(env["error"], "not_found")

    def test_learning_mode_block_surfaces_as_failed(self):
        # execute_intent's own fail-closed gate returns success=False
        with mock.patch(_EXEC, return_value=_action_result(
                success=False, message="I'm learning right now.",
                error="learning_mode_active")):
            env = execute_action(self.user, "create_task", {"title": "x"})
        self.assertEqual(env["status"], "failed")
        self.assertEqual(env["error"], "learning_mode_active")

    def test_execute_intent_raising_is_caught(self):
        with mock.patch(_EXEC, side_effect=RuntimeError("boom")):
            env = execute_action(self.user, "create_task", {"title": "x"})
        self.assertEqual(env["status"], "error")
        self.assertEqual(env["code"], "execution_error")

    def test_never_raises_on_garbage_params(self):
        with mock.patch(_EXEC, return_value=_action_result()):
            env = execute_action(self.user, "create_task", None)
        self.assertIn("status", env)

    # --- output contract --------------------------------------------------
    def test_output_json_serializable(self):
        with mock.patch(_EXEC, return_value=_action_result(
                created_object={"id": 1})):
            env = execute_action(self.user, "create_task", {"title": "x"})
        json.dumps(env)


class ActionExecutionDispatchTests(TestCase):
    """execute_action is reachable through the CoS tool dispatcher (Phase 6)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cos_act2@example.com", password="x")

    def test_dispatch_execute_action(self):
        from apps.ai.cos_services import dispatch_tool_call
        with mock.patch(_EXEC, return_value=_action_result(message="Task created.")):
            env = dispatch_tool_call(self.user, "execute_action",
                                     {"action": "create_task",
                                      "params": {"title": "Buy milk"}})
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["status"], "success")

    def test_dispatch_confirmation_flows_through(self):
        from apps.ai.cos_services import dispatch_tool_call
        with mock.patch(_EXEC) as ex:
            env = dispatch_tool_call(self.user, "execute_action",
                                     {"action": "mutate_task",
                                      "params": {"task_keyword": "x"}})
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["status"], "confirmation_required")
        ex.assert_not_called()
