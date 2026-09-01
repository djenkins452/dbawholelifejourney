# ==============================================================================
# File: apps/core/tests/test_cos_continuity_lifecycle.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Completed actions, subject supersession, and clarification continuity
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-01
# ==============================================================================
"""A completed action must stay completed, and an unresolved question must stay attached.

Production, 2026-09-01. An image-assisted food log succeeded. Two turns later the CoS
offered to log the same food again; a turn after that it bundled that already-logged food
into an unrelated request. Then a recurring-task reschedule asked "this occurrence or the
series?" — which was reported to the user as a FAILURE — and the user's answer, having no
intent to attach to, landed back on the old image.

Three deterministic gaps, all in WLJ:

  1. `record_turn()` knew about uploads and retrievals but had NO concept of a completed
     action, and confirmations resolve on a different turn that never called it at all.
  2. Nothing superseded an attachment subject once the write derived from it succeeded, so
     an old label stayed dominant for its whole turn window.
  3. A handler asking WHICH SCOPE was mapped to `error`, so no pending question was held.

These tests certify the CLASS, not the nouns. No provider calls anywhere.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface import conversation_state as cs
from apps.ai.models import AssistantConversation

User = get_user_model()


class ContinuityHarness(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cont@contract.test", password="x")
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _state(self):
        return cs.read(self.conv) or {}

    def _upload(self, artifact_id=101, filename="label.jpg"):
        cs.record_turn(self.conv, attachments=[
            {"artifact_id": artifact_id, "kind": "image", "filename": filename}])


class CompletedActionTests(ContinuityHarness):
    def test_a_completed_action_is_recorded_as_state(self):
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged 3 Food A for lunch.", target="Food A")
        done = self._state().get("completed_actions") or []
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["target"], "Food A")

    def test_a_completed_action_supersedes_a_consumed_attachment_subject(self):
        """The heart of it: the label stops being the live subject once it has been used."""
        self._upload()
        self.assertTrue((self._state().get("active_subject") or {}).get("artifact"))
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food A.", target="Food A")
        self.assertIsNone(self._state().get("active_subject"),
                          "the consumed attachment stayed the active subject")

    def test_completions_survive_later_turns(self):
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food A.", target="Food A")
        for _ in range(3):
            cs.record_turn(self.conv)
        self.assertTrue(self._state().get("completed_actions"),
                        "the completion was wiped by the end-of-turn rebuild")

    def test_completions_age_out_eventually(self):
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food A.", target="Food A")
        for _ in range(cs.MAX_COMPLETED_TURNS + 2):
            cs.record_turn(self.conv)
        self.assertFalse(self._state().get("completed_actions"),
                         "a completion stayed authoritative forever")

    def test_the_list_is_bounded(self):
        for i in range(20):
            cs.record_completed_action(self.conv, tool_name="log_food",
                                       summary=f"Logged Food {i}.", target=f"Food {i}")
        self.assertLessEqual(len(self._state().get("completed_actions") or []), 8)

    def test_a_non_attachment_subject_is_not_disturbed(self):
        """Only a CONSUMED attachment is superseded — a retrieved entity subject is not."""
        cs.record_turn(self.conv, retrieved_subject={
            "kind": "task", "ref": 55, "label": "Item C"})
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food A.", target="Food A")
        subj = self._state().get("active_subject") or {}
        self.assertEqual(subj.get("ref"), 55)


class PendingClarificationTests(ContinuityHarness):
    def test_a_question_is_held_open(self):
        cs.set_pending_clarification(
            self.conv, tool_name="mutate_task",
            question="This occurrence or the whole series?",
            args={"task_query": "Item C", "new_due_date": "Saturday"}, target="Item C")
        pc = self._state().get("pending_clarification") or {}
        self.assertEqual(pc["tool"], "mutate_task")
        self.assertEqual(pc["target"], "Item C")
        self.assertEqual(pc["args"]["new_due_date"], "Saturday",
                         "the original request must be preserved so the answer can refine it")

    def test_the_question_survives_the_next_turn(self):
        cs.set_pending_clarification(self.conv, tool_name="mutate_task",
                                     question="Which scope?", target="Item C")
        cs.record_turn(self.conv)
        self.assertTrue(self._state().get("pending_clarification"),
                        "the question was wiped the moment it was asked")

    def test_answering_clears_it(self):
        cs.set_pending_clarification(self.conv, tool_name="mutate_task",
                                     question="Which scope?", target="Item C")
        cs.clear_pending_clarification(self.conv)
        self.assertFalse(self._state().get("pending_clarification"))


class ClarificationIsNotAFailureTests(TestCase):
    """A handler asking which scope is not a broken action."""

    def test_scope_required_maps_to_clarification_not_error(self):
        from apps.ai.cos_services import action_interface as ai
        out = ai._map_result({"status": "failed", "code": "series_scope_required",
                              "message": "This occurrence or the whole series?"})
        self.assertEqual(out["status"], ai.CLARIFICATION_REQUIRED)
        self.assertNotEqual(out["status"], ai.ERROR)

    def test_a_genuine_failure_is_still_an_error(self):
        from apps.ai.cos_services import action_interface as ai
        out = ai._map_result({"status": "failed", "code": "not_found",
                              "message": "No such task."})
        self.assertEqual(out["status"], ai.ERROR)

    def test_clarification_codes_are_generic_not_object_specific(self):
        """No special-casing of any particular item or phrasing."""
        import pathlib
        src = pathlib.Path("apps/ai/cos_services/action_interface.py").read_text(
            encoding="utf-8")
        for noun in ("hair cut", "haircut", "beef", "bob evans", "just today"):
            self.assertNotIn(noun, src.lower())


class PromptPrecedenceTests(ContinuityHarness):
    """State the model cannot see is state that changes nothing."""

    def _lead(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        return svc._conversation_state_lead(
            {"conversation_state": cs.read(self.conv) or {}, "pending_confirmations": []})

    def test_completed_actions_are_surfaced_with_a_do_not_repeat_rule(self):
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged 3 Food A for lunch.", target="Food A")
        lead = self._lead()
        self.assertIn("ALREADY DONE", lead)
        self.assertIn("Food A", lead)
        self.assertIn("do NOT propose these", lead)

    def test_an_acknowledgment_is_named_as_not_a_request_to_repeat(self):
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food A.", target="Food A")
        self.assertIn("NOT a request to repeat", self._lead())

    def test_a_user_may_still_legitimately_repeat_something(self):
        """Do not over-correct into refusing genuine repeats."""
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food A.", target="Food A")
        self.assertIn("they must ASK", self._lead())

    def test_a_pending_question_outranks_other_state(self):
        self._upload()
        cs.set_pending_clarification(self.conv, tool_name="mutate_task",
                                     question="This occurrence or the whole series?",
                                     target="Item C")
        lead = self._lead()
        self.assertIn("AWAITING THEIR ANSWER", lead)
        self.assertLess(lead.index("AWAITING THEIR ANSWER"), lead.index("ACTIVE SUBJECT")
                        if "ACTIVE SUBJECT" in lead else len(lead),
                        "the open question must be stated before any lingering subject")
        self.assertIn("Item C", lead)
        self.assertIn("do NOT return to an earlier subject", lead)


class FullLifecycleTests(ContinuityHarness):
    """The production sequence, as a class — no beef sticks, no Hair Cut, no 'Just today'."""

    def test_image_write_then_acknowledgment_then_new_write_then_domain_switch(self):
        # A — image-assisted write, confirmed, verified
        self._upload(artifact_id=900, filename="food-label.jpg")
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged 3 Food A for lunch.", target="Food A")

        # the attachment is consumed the moment the write it fed succeeds
        self.assertIsNone(self._state().get("active_subject"))

        # B — a conversational acknowledgment ("nice one")
        cs.record_turn(self.conv)
        state = self._state()
        self.assertTrue(any(d.get("target") == "Food A"
                            for d in state.get("completed_actions") or []),
                        "the completed write is no longer known, so it can be re-proposed")
        self.assertIsNone(state.get("active_subject"),
                          "the old attachment came back as the active subject")

        # C/D — an unrelated new write, confirmed
        cs.record_turn(self.conv)
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged Food B for dinner.", target="Food B")
        targets = [d.get("target") for d in self._state().get("completed_actions") or []]
        self.assertIn("Food A", targets)
        self.assertIn("Food B", targets)

        # E/F — domain switch to a recurring item; the handler asks which scope
        cs.record_turn(self.conv, retrieved_subject={
            "kind": "task", "ref": 77, "label": "Item C"})
        cs.set_pending_clarification(
            self.conv, tool_name="mutate_task",
            question="This occurrence or the whole series?",
            args={"task_query": "Item C", "new_due_date": "Saturday"}, target="Item C")

        # G — a short reply. It must land on Item C, not on the old image or Food A.
        from apps.ai.model_interface.service import ModelInterfaceService
        lead = ModelInterfaceService(self.user)._conversation_state_lead(
            {"conversation_state": self._state(), "pending_confirmations": []})
        self.assertIn("AWAITING THEIR ANSWER", lead)
        self.assertIn("Item C", lead)
        self.assertIn("mutate_task", lead)
        self.assertNotIn("food-label.jpg", lead,
                         "the consumed attachment resurfaced after a domain switch")
        self.assertIn("do NOT propose these", lead,
                      "completed writes must still be marked do-not-repeat")


class ConfirmSeamTests(TestCase):
    """Completion must be recorded where confirmations actually resolve."""

    def test_the_resolver_records_completion_on_success(self):
        import pathlib
        src = pathlib.Path("apps/ai/cos_services/action_interface.py").read_text(
            encoding="utf-8")
        seam = src[src.index('out["confirmation_id"] = confirmation_id'):]
        self.assertIn("record_completed_action", seam)
        self.assertIn('out.get("status") == OK', seam,
                      "completion must be recorded only for a VERIFIED success")

    def test_completion_recording_can_never_break_a_write(self):
        import pathlib
        src = pathlib.Path("apps/ai/cos_services/action_interface.py").read_text(
            encoding="utf-8")
        seam = src[src.index("COMPLETED-ACTION CONTINUITY"):]
        # Window sized to the block, not guessed: end at the audit call that
        # follows it, so the assertion cannot pass or fail on slice length.
        block = seam[:seam.index("record_tool_call(")]
        self.assertIn("except Exception", block)
        self.assertIn("never break a write", block)


class CrossUserIsolationTests(TestCase):
    def test_state_is_per_conversation(self):
        a = User.objects.create_user(email="iso-a@contract.test", password="x")
        b = User.objects.create_user(email="iso-b@contract.test", password="x")
        ca = AssistantConversation.get_or_create_active(a)
        cb = AssistantConversation.get_or_create_active(b)
        cs.record_completed_action(ca, tool_name="log_food", summary="A's write.",
                                   target="Food A")
        self.assertFalse((cs.read(cb) or {}).get("completed_actions"),
                         "one conversation's completions leaked into another")
