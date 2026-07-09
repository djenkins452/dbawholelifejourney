# ==============================================================================
# File: apps/ai/tests/test_action_interface.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Action interface (Pillar 2) — STATEFUL server-side confirmation.
# ==============================================================================
"""
Tests for apps/ai/cos_services/action_interface.py.

The eliminate-the-class guarantee: when an action needs confirmation, WLJ STORES it
server-side; a later confirm executes the STORED action — the model never reconstructs
the confirmed re-call. `execute_action` is mocked to drive the flow deterministically;
the real cache-based pending store is exercised.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.cos_services import action_interface as ai
from apps.ai.models import ToolCallLog

User = get_user_model()

_EXEC = "apps.ai.cos_services.action_interface.execute_action"


def _fake_execute(user, action, params):
    """Mirror real execute_action: needs confirmation unless confirmed=True."""
    if params.get("confirmed"):
        return {"status": "success", "action": action,
                "message": "Moved 'Check on Melissa's Pillow' to 9:00 PM."}
    return {"status": "confirmation_required", "action": action,
            "message": "This changes existing data and needs confirmation."}


class ActionInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="act@example.com", password="x")

    def setUp(self):
        cache.clear()  # pending store is cache-backed

    def _pending(self):
        from apps.ai.intent_service import IntentService
        return IntentService().get_pending_confirmation(self.user)

    def test_confirmation_required_stores_pending_server_side(self):
        with mock.patch(_EXEC, side_effect=_fake_execute):
            out = ai.request_action(self.user, "mutate_task",
                                    {"id": 5, "time": "21:00"}, turn_id="t1")
        self.assertEqual(out["status"], ai.CONFIRMATION_REQUIRED)
        self.assertTrue(out["confirmation"]["pending"])
        # The action is now held server-side (the model did NOT keep it).
        pending = self._pending()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["intent_type"], "mutate_task")
        self.assertEqual(pending["parameters"]["id"], 5)

    def test_confirm_executes_the_stored_action_and_clears(self):
        with mock.patch(_EXEC, side_effect=_fake_execute) as m:
            ai.request_action(self.user, "mutate_task", {"id": 5, "time": "21:00"},
                              turn_id="t1")
            out = ai.resolve_pending_action(self.user, confirm=True, turn_id="t1")

        self.assertEqual(out["status"], ai.OK)
        self.assertIn("9:00 PM", out["result"])          # narrated from the REAL result
        # The executing call carried confirmed=True + the STORED params — supplied by
        # WLJ, never reconstructed by the model.
        exec_call = m.call_args_list[-1]
        _, exec_action, exec_params = exec_call.args
        self.assertEqual(exec_action, "mutate_task")
        self.assertTrue(exec_params["confirmed"])
        self.assertEqual(exec_params["id"], 5)
        self.assertEqual(exec_params["time"], "21:00")
        # Pending cleared after resolution.
        self.assertIsNone(self._pending())

    def test_decline_cancels_without_executing(self):
        with mock.patch(_EXEC, side_effect=_fake_execute) as m:
            ai.request_action(self.user, "mutate_task", {"id": 5}, turn_id="t1")
            calls_after_request = m.call_count
            out = ai.resolve_pending_action(self.user, confirm=False, turn_id="t1")
            # No execution happened on decline.
            self.assertEqual(m.call_count, calls_after_request)
        self.assertEqual(out["status"], ai.DECLINED)
        self.assertIsNone(self._pending())

    def test_resolve_with_nothing_pending_is_honest(self):
        out = ai.resolve_pending_action(self.user, confirm=True)
        self.assertEqual(out["status"], ai.ERROR)
        self.assertEqual(out["code"], "nothing_pending")

    def test_non_confirmation_action_executes_immediately(self):
        with mock.patch(_EXEC, return_value={"status": "success",
                                             "message": "Logged.", "action": "log_x"}):
            out = ai.request_action(self.user, "log_x", {"v": 1}, turn_id="t2")
        self.assertEqual(out["status"], ai.OK)
        self.assertEqual(out["result"], "Logged.")
        self.assertIsNone(self._pending())   # nothing stored for a non-confirm action

    def test_failed_execution_reports_the_real_reason(self):
        with mock.patch(_EXEC, return_value={"status": "failed",
                                             "message": "Task not found.",
                                             "code": "not_found", "action": "mutate_task"}):
            out = ai.request_action(self.user, "mutate_task", {"id": 999})
        self.assertEqual(out["status"], ai.ERROR)
        self.assertEqual(out["result"], "Task not found.")

    def test_actions_are_audited(self):
        with mock.patch(_EXEC, side_effect=_fake_execute):
            ai.request_action(self.user, "mutate_task", {"id": 5}, turn_id="taudit")
            ai.resolve_pending_action(self.user, confirm=True, turn_id="taudit")
        rows = ToolCallLog.objects.filter(user=self.user, turn_id="taudit", kind="action")
        self.assertEqual(rows.count(), 2)
