# ==============================================================================
# File: apps/ai/tests/test_action_interface.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Action interface (Pillar 2) — BOUND confirmation transactions.
# ==============================================================================
"""
Tests for the bound-confirmation action interface (Blocker 1 hardening).

Each confirmation has its own id; resolve executes a SPECIFIC confirmation, never
"whatever is stored." `execute_action` is mocked to drive the flow; the real bound
confirmation cache store is exercised.
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
    if params.get("confirmed"):
        return {"status": "success", "action": action,
                "message": f"Executed {action}."}
    return {"status": "confirmation_required", "action": action,
            "message": "needs confirmation"}


class BoundConfirmationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="act@example.com", password="x")

    def setUp(self):
        cache.clear()

    def test_request_returns_a_bound_confirmation_id(self):
        with mock.patch(_EXEC, side_effect=_fake_execute):
            out = ai.request_action(self.user, "mutate_task",
                                    {"id": 5, "time": "21:00"}, turn_id="t1")
        self.assertEqual(out["status"], ai.CONFIRMATION_REQUIRED)
        cid = out["confirmation"]["confirmation_id"]
        self.assertTrue(cid)
        self.assertIn("mutate_task", out["confirmation"]["summary"])

    def test_confirm_by_id_executes_that_action_and_consumes_it(self):
        with mock.patch(_EXEC, side_effect=_fake_execute) as m:
            req = ai.request_action(self.user, "mutate_task", {"id": 5}, turn_id="t1")
            cid = req["confirmation"]["confirmation_id"]
            out = ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="t1")
        self.assertEqual(out["status"], ai.OK)
        # executed with confirmed=true + the STORED params
        _, exec_action, exec_params = m.call_args_list[-1].args
        self.assertEqual(exec_action, "mutate_task")
        self.assertTrue(exec_params["confirmed"])
        self.assertEqual(exec_params["id"], 5)
        # single-use: the same id no longer resolves
        again = ai.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(again["code"], "no_matching_confirmation")

    def test_confused_deputy_is_prevented(self):
        # Two requests → two distinct ids. Resolving A executes A, never B.
        with mock.patch(_EXEC, side_effect=_fake_execute) as m:
            a = ai.request_action(self.user, "mutate_task", {"id": 1})["confirmation"]
            b = ai.request_action(self.user, "create_task", {"title": "B"})["confirmation"]
            self.assertNotEqual(a["confirmation_id"], b["confirmation_id"])
            ai.resolve_pending_action(self.user, a["confirmation_id"], confirm=True)
        _, exec_action, exec_params = m.call_args_list[-1].args
        self.assertEqual(exec_action, "mutate_task")   # A, not B
        self.assertEqual(exec_params["id"], 1)
        # B is still pending and independently resolvable.
        from apps.ai.model_interface import confirmation
        self.assertIsNotNone(confirmation.get(self.user, b["confirmation_id"]))

    def test_missing_or_wrong_id_fails_honestly(self):
        self.assertEqual(
            ai.resolve_pending_action(self.user, "does-not-exist", confirm=True)["code"],
            "no_matching_confirmation")
        self.assertEqual(
            ai.resolve_pending_action(self.user, None, confirm=True)["code"],
            "no_matching_confirmation")

    def test_decline_cancels_without_executing(self):
        with mock.patch(_EXEC, side_effect=_fake_execute) as m:
            cid = ai.request_action(self.user, "mutate_task", {"id": 5})[
                "confirmation"]["confirmation_id"]
            calls_after_request = m.call_count
            out = ai.resolve_pending_action(self.user, cid, confirm=False)
            self.assertEqual(m.call_count, calls_after_request)  # no execution
        self.assertEqual(out["status"], ai.DECLINED)
        from apps.ai.model_interface import confirmation
        self.assertIsNone(confirmation.get(self.user, cid))  # consumed

    def test_non_confirmation_action_executes_immediately(self):
        with mock.patch(_EXEC, return_value={"status": "success",
                                             "message": "Logged.", "action": "log_x"}):
            out = ai.request_action(self.user, "log_x", {"v": 1})
        self.assertEqual(out["status"], ai.OK)
        self.assertNotIn("confirmation", out)

    def test_failed_execution_reports_the_real_reason(self):
        with mock.patch(_EXEC, return_value={"status": "failed",
                                             "message": "Task not found.",
                                             "code": "not_found", "action": "mutate_task"}):
            out = ai.request_action(self.user, "mutate_task", {"id": 999})
        self.assertEqual(out["status"], ai.ERROR)
        self.assertEqual(out["result"], "Task not found.")

    def test_actions_are_audited(self):
        with mock.patch(_EXEC, side_effect=_fake_execute):
            cid = ai.request_action(self.user, "mutate_task", {"id": 5},
                                    turn_id="taudit")["confirmation"]["confirmation_id"]
            ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="taudit")
        rows = ToolCallLog.objects.filter(user=self.user, turn_id="taudit", kind="action")
        self.assertEqual(rows.count(), 2)
