# ==============================================================================
# File: apps/core/tests/test_action_lifecycle_multiturn_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Multi-turn action lifecycle — state transitions ACROSS turns
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""Multi-turn action lifecycle contract.

WHY THIS FILE EXISTS: every fix in the 2026-08-18 action-integrity incident passed its
own unit tests while the production CONVERSATION kept failing. The defects live in the
transitions BETWEEN turns — a stale claim carried forward, a confirmation that spans
turns, an envelope rebuilt after a mutation — and isolated helper tests cannot see them.

This harness carries real runtime state (user, conversation, pending confirmation,
canonical rows, rebuilt envelope) across a sequence of turns and asserts the TRANSITIONS.

Nothing here is Shower-specific.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class ActionLifecycleHarness(TestCase):
    """Shared multi-turn harness: one user, one conversation, one executable item."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="lc@contract.test", password="x")
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.use_model_interface = True
        prefs.use_model_interface_writes = True
        prefs.assistant_confirm_actions = True
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)

        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Daily Rhythm", time_of_day="morning")
        self.item = RoutineSchedule.objects.create(
            routine=self.routine, name="Rinse Cycle",
            scheduled_time=datetime.time(7, 0), is_active=True,
            days_of_week="0,1,2,3,4,5,6")
        self.conv = AssistantConversation.get_or_create_active(self.user)

    # -- helpers that mirror what a real turn does -------------------------
    def _fresh_user(self):
        return User.objects.get(pk=self.user.pk)

    def _canonical_complete(self):
        from apps.core.execution.completion_service import is_routine_item_complete
        from apps.life.models import RoutineSchedule
        sched = RoutineSchedule.objects.get(pk=self.item.pk)
        return bool(is_routine_item_complete(self._fresh_user(), sched, self.today))

    def _say(self, text):
        """A user turn that hits the deterministic pre-parser, as the gateway does."""
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        return resolve_typed_confirmation(self._fresh_user(), self.conv.id, text,
                                          turn_id="t", surface="chat_stream")

    def _request_completion(self):
        """Turn A: the CoS proposes the write and WLJ binds a confirmation."""
        from apps.ai.cos_services.action_execution import confirmation_required_for
        from apps.ai.cos_services.action_interface import request_confirmation_for
        from apps.ai.model_interface import confirmation as _confirm
        user = self._fresh_user()
        self.assertTrue(confirmation_required_for(user, "complete_execution_item"))
        gate = request_confirmation_for(
            user, "complete_execution_item",
            {"source_type": "routine_item", "source_id": self.item.pk,
             "title": self.item.name},
            conversation_id=self.conv.id)
        _confirm.bind_conversation(user, self.conv.id)
        return gate

    def _envelope_says_complete(self):
        """What CURRENT truth would tell the model this turn (the freshness question)."""
        from apps.core.execution.today_execution import build_today_execution
        items = build_today_execution(self._fresh_user())["items"]
        mine = [i for i in items
                if i.get("source_type") == "routine_item"
                and i.get("source_id") == self.item.pk]
        if not mine:
            return None
        return bool(mine[0].get("completed_today"))


class FullLifecycleTests(ActionLifecycleHarness):
    """A → B → C → D across turns, with canonical state driving every assertion."""

    def test_turn_a_binds_without_mutating(self):
        gate = self._request_completion()
        self.assertEqual(gate["status"], "confirmation_required")
        self.assertFalse(self._canonical_complete(),
                         "Turn A mutated before the user authorized anything")

    def test_turn_b_yes_executes_and_canonical_truth_agrees(self):
        self._request_completion()
        out = self._say("Yes")
        self.assertIsNotNone(out, "the bound confirmation was not resolved deterministically")
        self.assertEqual(out["status"], "ok", out)
        self.assertTrue(self._canonical_complete())
        self.assertTrue(self._envelope_says_complete(),
                        "canonical state changed but the envelope the NEXT turn reads "
                        "still shows it incomplete")

    def test_turn_c_reversal_is_immediately_visible_to_the_next_turn(self):
        """The envelope must not serve a stale 'complete' after truth changes back."""
        from apps.core.execution.execution_completion import reverse_by_identity
        self._request_completion()
        self._say("Yes")
        self.assertTrue(self._envelope_says_complete())

        reverse_by_identity(self._fresh_user(), "routine_item", self.item.pk,
                            self.today, requested_target=self.item.name)
        self.assertFalse(self._canonical_complete())
        self.assertFalse(self._envelope_says_complete(), (
            "STALE ENVELOPE: canonical truth says incomplete but the next turn would be "
            "told it is complete — the model would then 'correctly' claim already-complete "
            "from data WLJ handed it"))

    def test_turn_d_a_silent_no_op_leaves_current_truth_incomplete(self):
        """The production shape: a write that reported success but changed nothing."""
        from unittest import mock
        from apps.core.execution.execution_completion import complete_by_identity
        with mock.patch("apps.life.services.routine_helpers.toggle_routine_completion"):
            out = complete_by_identity(self._fresh_user(), "routine_item", self.item.pk,
                                       self.today, requested_target=self.item.name)
        self.assertEqual(out["status"], "postcondition_failed")
        self.assertFalse(self._canonical_complete())
        self.assertFalse(self._envelope_says_complete(), (
            "after a failed write the next turn must still see the item as INCOMPLETE"))

    def test_turn_d_fresh_request_re_binds_a_new_confirmation(self):
        """A later identical request is a NEW write decision, not the old authorization."""
        from apps.ai.model_interface import confirmation as _confirm
        first = self._request_completion()
        first_cid = (first.get("confirmation") or {}).get("confirmation_id")
        self._say("Yes")
        self.assertTrue(self._canonical_complete())

        # truth changes back; the user asks again
        from apps.core.execution.execution_completion import reverse_by_identity
        reverse_by_identity(self._fresh_user(), "routine_item", self.item.pk,
                            self.today, requested_target=self.item.name)

        second = self._request_completion()
        second_cid = (second.get("confirmation") or {}).get("confirmation_id")
        self.assertNotEqual(first_cid, second_cid,
                            "a NEW request reused the OLD confirmation id")
        self.assertFalse(self._canonical_complete(),
                         "the new request mutated before authorization")
        self.assertIsNone(_confirm.get(self._fresh_user(), first_cid),
                          "the consumed confirmation is still live and replayable")

    def test_consumed_confirmation_cannot_authorize_a_later_request(self):
        first = self._request_completion()
        cid = (first.get("confirmation") or {}).get("confirmation_id")
        self._say("Yes")
        from apps.ai.cos_services.action_interface import resolve_pending_action
        replay = resolve_pending_action(self._fresh_user(), cid, confirm=True)
        self.assertNotEqual(replay.get("status"), "ok",
                            "a consumed confirmation authorized a second write")


class CurrentTruthOutranksHistoryTests(ActionLifecycleHarness):
    """THE 17:50 CLASS: a prior claim must never stand in for current state.

    Production turn c1e0005f asserted "already marked as complete" with ZERO tool calls,
    sourced from earlier assistant prose. These tests pin the deterministic half of the
    invariant: whatever the transcript says, the CURRENT-TRUTH surfaces the next turn
    reads must report the real state.
    """

    def _persist_assistant_claim(self, text):
        from apps.ai.models import AssistantMessage
        return AssistantMessage.objects.create(
            conversation=self.conv, role="assistant", content=text,
            message_type="text")

    def test_a_false_prior_claim_does_not_change_current_truth(self):
        self._persist_assistant_claim(f"'{self.item.name}' is marked as complete.")
        self.assertFalse(self._canonical_complete(),
                         "assistant prose changed canonical state")
        self.assertFalse(self._envelope_says_complete(), (
            "the next turn's CURRENT-TRUTH surface reports complete purely because a "
            "previous message said so"))

    def test_history_and_current_truth_disagree_visibly(self):
        """The evidence the model needs must be present and must contradict the prose."""
        self._request_completion()
        self._say("Yes")
        self._persist_assistant_claim(f"'{self.item.name}' is marked as complete.")
        from apps.core.execution.execution_completion import reverse_by_identity
        reverse_by_identity(self._fresh_user(), "routine_item", self.item.pk,
                            self.today, requested_target=self.item.name)

        self.assertFalse(self._canonical_complete())
        self.assertIs(self._envelope_says_complete(), False, (
            "the transcript claims complete and current truth says incomplete — the "
            "envelope MUST carry the incomplete state so the model can be held to it"))

    def test_prior_action_result_is_history_not_current_state(self):
        """A recorded ToolCallLog result must not be readable as present-tense truth."""
        from apps.ai.models import ToolCallLog
        self._request_completion()
        self._say("Yes")
        from apps.core.execution.execution_completion import reverse_by_identity
        reverse_by_identity(self._fresh_user(), "routine_item", self.item.pk,
                            self.today, requested_target=self.item.name)

        recorded = ToolCallLog.objects.filter(
            user=self.user, tool_name="complete_execution_item").exists()
        self.assertTrue(recorded, "the historical action result should still exist")
        self.assertFalse(self._canonical_complete(),
                         "a historical 'recorded' result was treated as current state")
