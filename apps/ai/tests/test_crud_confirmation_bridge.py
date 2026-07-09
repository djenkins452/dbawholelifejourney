# ==============================================================================
# File: apps/ai/tests/test_crud_confirmation_bridge.py
# Description: CRUD-CONFIRMATION COMPLETION for the CoS pipeline (Layer-3 bridge). The CoS
#   could INITIATE a mutation confirmation (execute_action → confirmation_required) but not
#   COMPLETE it on the next turn. The bridge stores the pending action on confirmation, then
#   on "yes" executes it once (reusing intent_service.store/handle_crud_confirmation), clears
#   it, and reports the real success/failure. Ordinary turns are untouched.
# ==============================================================================
from datetime import time as dtime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.users.models import TermsAcceptance
from apps.ai.chatgpt_cos.crud_bridge import (
    maybe_resolve_pending_crud, maybe_store_pending_crud)
from apps.ai.intent_service import IntentService

User = get_user_model()


def _mkuser(email):
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _move_args(title="Check on Melissa's Pillow", hhmm="21:00"):
    return {"action": "mutate_task",
            "params": {"action": "update", "task_query": title, "new_scheduled_time": hhmm}}


class CrudConfirmationBridgeTests(TestCase):
    def setUp(self):
        from apps.life.models import Task
        self.u = _mkuser("crudbridge@test.com")
        self.today = timezone.localdate()
        self.task = Task.objects.create(
            user=self.u, title="Check on Melissa's Pillow", status='active',
            due_date=self.today, is_recurring=False, scheduled_time=None)
        self.svc = IntentService()

    def test_move_asks_for_confirmation_and_stores_pending(self):
        from apps.ai.cos_services import dispatch_tool_call
        # (1) The move is gated: execute_action returns confirmation_required, no side effect.
        res = dispatch_tool_call(self.u, "execute_action", _move_args())
        self.assertEqual(res["result"]["status"], "confirmation_required")
        self.task.refresh_from_db()
        self.assertIsNone(self.task.scheduled_time)               # not moved yet
        # The bridge stores the pending action for the next turn.
        maybe_store_pending_crud(self.u, "execute_action", _move_args(), res, "move it to 9pm")
        self.assertIsNotNone(self.svc.get_pending_crud_action(self.u))

    def test_yes_executes_and_moves_the_task(self):
        # Simulate turn 1 having stored the pending action, then the user says "yes".
        self.svc.store_pending_crud_action(self.u, {
            "intent_type": "mutate_task", "parameters": _move_args()["params"],
            "original_intent": "mutate_task", "confirmation_message": "Confirm?"})
        out = maybe_resolve_pending_crud(self.u, "yes")
        # (2)+(6) executed → a real completion message; (3) the time actually changed.
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "crud_confirmation")
        self.assertIn("9:00 PM", out["answer"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.scheduled_time, dtime(21, 0))
        # (4) the pending confirmation is cleared.
        self.assertIsNone(self.svc.get_pending_crud_action(self.u))

    def test_second_yes_does_not_execute_again(self):
        self.svc.store_pending_crud_action(self.u, {
            "intent_type": "mutate_task", "parameters": _move_args()["params"],
            "original_intent": "mutate_task", "confirmation_message": "Confirm?"})
        maybe_resolve_pending_crud(self.u, "yes")
        self.task.refresh_from_db()
        self.assertEqual(self.task.scheduled_time, dtime(21, 0))
        # (5) a SECOND "yes" has nothing pending → the bridge declines; no re-execution.
        out2 = maybe_resolve_pending_crud(self.u, "yes")
        self.assertIsNone(out2)
        self.task.refresh_from_db()
        self.assertEqual(self.task.scheduled_time, dtime(21, 0))   # unchanged (moved once)

    def test_failure_reports_the_actual_error(self):
        # A pending action whose target no longer resolves → "yes" surfaces the real failure,
        # not a false success.
        self.svc.store_pending_crud_action(self.u, {
            "intent_type": "mutate_task",
            "parameters": {"action": "update", "task_query": "Nonexistent Task XYZ",
                           "new_scheduled_time": "21:00"},
            "original_intent": "mutate_task", "confirmation_message": "Confirm?"})
        out = maybe_resolve_pending_crud(self.u, "yes")
        self.assertIsNotNone(out)
        self.assertNotIn("9:00 PM", out["answer"])                 # did not falsely succeed
        self.assertIsNone(self.svc.get_pending_crud_action(self.u))  # cleared regardless

    def test_non_confirmation_conversations_unaffected(self):
        # (6) No pending action → the bridge is a no-op for any message.
        self.assertIsNone(maybe_resolve_pending_crud(self.u, "what's my weight?"))
        self.assertIsNone(maybe_resolve_pending_crud(self.u, "yes"))
        # A non-mutation tool result never stores a pending.
        maybe_store_pending_crud(self.u, "get_domain_state", {}, {"result": {"status": "ok"}})
        self.assertIsNone(self.svc.get_pending_crud_action(self.u))
