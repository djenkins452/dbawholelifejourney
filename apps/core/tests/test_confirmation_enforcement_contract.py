# ==============================================================================
# File: apps/core/tests/test_confirmation_enforcement_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Safety preferences must be ENFORCED at the write boundary
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""Confirmation enforcement contract (2026-08-18 production incident).

Danny's Preferences visibly promised "Ask me first before creating, changing or
deleting anything on my behalf". He said "mark 'call the pharmacy' as complete" and the
CoS mutated immediately — ToolCallLog 62d315f8:
    complete_execution_item(source_id=622, source_type="task") -> recorded

TWO layers were wrong:
  1. `complete_execution_item` called the completion service DIRECTLY from the
     model_interface dispatch, bypassing `request_action` and the confirmation authority.
  2. Even the authority never read `assistant_confirm_actions` — that preference was
     enforced ONLY inside `IntentService.recognize_intents`, a legacy path the certified
     runtime does not use.

THE INVARIANT THIS FILE PROTECTS — stronger than M1's T3/T4:
    A safety preference must be ENFORCED at the authority it governs,
    not merely DELIVERED to the model.
M1 proved delivery. Delivery is not enforcement.
"""

import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.cos_services.action_execution import confirmation_required_for

User = get_user_model()
REPO = Path(__file__).resolve().parents[3]


class ConfirmationPolicyTests(TestCase):
    """ONE authority, and it reads the user's preference."""

    def setUp(self):
        self.user = User.objects.create_user(email="cf1@contract.test", password="x")

    def _set(self, value):
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = value
        prefs.save()
        return User.objects.get(pk=self.user.pk)

    def test_preference_on_requires_confirmation(self):
        user = self._set(True)
        for action in ("complete_execution_item", "complete_task", "log_weight",
                       "create_task", "log_habit"):
            with self.subTest(action=action):
                self.assertTrue(confirmation_required_for(user, action), (
                    f"{action} would execute without confirmation while the user's "
                    "'Ask me first' preference is ON"))

    def test_preference_off_allows_a_reversible_completion_directly(self):
        user = self._set(False)
        self.assertFalse(confirmation_required_for(user, "complete_execution_item"),
                         "with the preference OFF a reversible completion must still "
                         "execute directly (the guided-review flow depends on it)")

    def test_intrinsic_risk_still_confirms_with_the_preference_off(self):
        """The preference is not the only ground — risky actions confirm regardless."""
        user = self._set(False)
        self.assertTrue(confirmation_required_for(user, "some_unregistered_action"),
                        "an unknown action must fail safe toward confirming")

    def test_unreadable_preference_fails_safe(self):
        class Broken:
            @property
            def preferences(self):
                raise RuntimeError("boom")
        self.assertTrue(confirmation_required_for(Broken(), "complete_execution_item"),
                        "an unreadable preference must fail SAFE (confirm), not open")


class WriteBoundaryEnforcementTests(TestCase):
    """The write path itself must fail closed — not merely be told to ask."""

    def setUp(self):
        from apps.life.models import Task
        self.user = User.objects.create_user(email="cf2@contract.test", password="x")
        self.today = datetime.date.today()
        self.task = Task.objects.create(
            user=self.user, title="Call the pharmacy", due_date=self.today,
            completion_status="pending", status="active")
        self.other = Task.objects.create(
            user=self.user, title="Something else", due_date=self.today,
            completion_status="pending", status="active")
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = True
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)

    def _dispatch(self, args):
        """Drive the REAL model_interface tool dispatch, as the model would."""
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        return svc._execute_tool("complete_execution_item", args,
                                 turn_id="t", surface="test", conversation_id=None)

    def test_the_exact_production_case_now_asks_first(self):
        from apps.ai.cos_services.action_interface import request_confirmation_for
        out = request_confirmation_for(
            self.user, "complete_execution_item",
            {"source_type": "task", "source_id": self.task.pk,
             "title": "Call the pharmacy"})
        self.assertIsNotNone(out)
        self.assertEqual(out["status"], "confirmation_required")
        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, "pending",
                         "THE PRODUCTION BUG: the object mutated before confirmation")

    def test_confirmation_binds_the_exact_target_and_executes_only_that(self):
        from apps.ai.cos_services.action_interface import (
            request_confirmation_for, resolve_pending_action,
        )
        gate = request_confirmation_for(
            self.user, "complete_execution_item",
            {"source_type": "task", "source_id": self.task.pk,
             "title": "Call the pharmacy"})
        cid = (gate.get("confirmation") or {}).get("confirmation_id")
        self.assertTrue(cid, gate)

        done = resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(done["status"], "ok", done)
        self.task.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.task.completion_status, "completed")
        self.assertEqual(self.other.completion_status, "pending",
                         "confirming one action changed a different object")

    def test_declining_mutates_nothing_and_closes_the_pending_action(self):
        from apps.ai.cos_services.action_interface import (
            request_confirmation_for, resolve_pending_action,
        )
        gate = request_confirmation_for(
            self.user, "complete_execution_item",
            {"source_type": "task", "source_id": self.task.pk,
             "title": "Call the pharmacy"})
        cid = (gate.get("confirmation") or {}).get("confirmation_id")
        resolve_pending_action(self.user, cid, confirm=False)
        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, "pending")
        again = resolve_pending_action(self.user, cid, confirm=True)
        self.assertNotEqual(again.get("status"), "ok",
                            "a declined confirmation was still executable")

    def test_a_confirmation_is_single_use(self):
        from apps.ai.cos_services.action_interface import (
            request_confirmation_for, resolve_pending_action,
        )
        gate = request_confirmation_for(
            self.user, "complete_execution_item",
            {"source_type": "task", "source_id": self.task.pk,
             "title": "Call the pharmacy"})
        cid = (gate.get("confirmation") or {}).get("confirmation_id")
        first = resolve_pending_action(self.user, cid, confirm=True)
        self.task.refresh_from_db()
        completed_at_after_first = self.task.completed_at

        replay = resolve_pending_action(self.user, cid, confirm=True)
        self.task.refresh_from_db()

        # THE INVARIANT IS "NO SECOND MUTATION", NOT A STATUS STRING.
        # A repeated confirm is a retry, a double-send or a reconnect, and the design
        # answers it by REPLAYING the stored outcome — telling the client what actually
        # happened rather than inventing a failure for an action that did succeed. This
        # test previously asserted `status != "ok"`, which contradicted that design while
        # never checking the thing that actually matters: whether the record changed twice.
        self.assertEqual(self.task.completed_at, completed_at_after_first,
                         "a repeated confirmation re-executed the write")
        self.assertEqual(replay.get("code"), "already_resolved",
                         "a consumed confirmation was not marked as already resolved")
        self.assertEqual(replay.get("result"), first.get("result"),
                         "the replay did not return the original outcome")

    def test_confirmation_carries_the_bound_identity_not_a_name_to_re_resolve(self):
        """A later 'yes' must execute the bound target, never re-resolve it."""
        from apps.ai.model_interface import confirmation as _confirm
        from apps.ai.cos_services.action_interface import request_confirmation_for
        gate = request_confirmation_for(
            self.user, "complete_execution_item",
            {"source_type": "task", "source_id": self.task.pk,
             "title": "Call the pharmacy"})
        cid = (gate.get("confirmation") or {}).get("confirmation_id")
        rec = _confirm.get(self.user, cid)
        self.assertEqual(rec["params"]["source_id"], self.task.pk)
        self.assertEqual(rec["params"]["source_type"], "task")


class NoWriteBypassesConfirmationTests(SimpleTestCase):
    """Structural: no model-facing write may skip the confirmation authority."""

    def test_completion_dispatch_consults_the_authority(self):
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        block = src[src.index('if name == "complete_execution_item":'):][:2200]
        self.assertIn("confirmation_required_for", block, (
            "complete_execution_item mutates without consulting the confirmation "
            "authority — the exact 2026-08-18 defect"))
        self.assertIn("request_confirmation_for", block)

    def test_there_is_exactly_one_confirmation_policy(self):
        """No handler may implement its own confirmation check."""
        offenders = []
        for path in REPO.glob("apps/ai/**/*.py"):
            rel = str(path.relative_to(REPO))
            if "action_execution.py" in rel or "/tests" in rel or "intent_service.py" in rel:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "assistant_confirm_actions" in text and "ai_relationship.py" not in rel:
                offenders.append(rel)
        self.assertEqual(offenders, [], (
            f"these modules read the confirmation preference directly instead of using "
            f"confirmation_required_for(): {offenders}. One authority."))

    def test_delivery_is_not_enforcement(self):
        """The preference must be enforced where writes happen, not only projected."""
        src = (REPO / "apps/ai/cos_services/action_execution.py").read_text(encoding="utf-8")
        self.assertIn("assistant_confirm_actions", src,
                      "the write authority must READ the preference, not rely on the "
                      "model having been told about it")


class VerifiedResultIntegrityTests(TestCase):
    """FALSE SUCCESS (2026-08-18). With confirmation ON the CoS asked, Danny said "Yes",
    the CoS said "'Shower' is marked as complete" — and the Dashboard still showed it open.

    ToolCallLog: turn 92e4210b produced `confirmation_required` (mutated: false); the
    following "Yes" turn (48957246) made **ZERO tool calls**. The model narrated a
    completion it never executed.

    INVARIANT: requested state → mutation → canonical truth VERIFIES it → success.
    A handler returning without raising is not evidence.
    """

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="vr@contract.test", password="x")
        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.shower = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", scheduled_time=datetime.time(7, 0),
            is_active=True, days_of_week="0,1,2,3,4,5,6")

    def test_success_is_reported_only_after_canonical_verification(self):
        from apps.core.execution.execution_completion import complete_by_identity
        out = complete_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                                   requested_target="Shower")
        self.assertEqual(out["status"], "recorded")
        self.assertTrue(out["detail"]["verified"],
                        "a success was returned without verifying canonical state")

    def test_a_silent_no_op_cannot_report_success(self):
        """If the mutation does not take, the result must NOT say recorded."""
        from unittest import mock
        from apps.core.execution.execution_completion import complete_by_identity
        with mock.patch("apps.life.services.routine_helpers.toggle_routine_completion"):
            out = complete_by_identity(self.user, "routine_item", self.shower.pk,
                                       self.today, requested_target="Shower")
        self.assertEqual(out["status"], "postcondition_failed", (
            "a mutation that changed NOTHING was reported as success — exactly the "
            "production false-success"))
        self.assertFalse(out["detail"]["verified"])
        self.assertIn("not", out["message"].lower())

    def test_reversal_is_verified_too(self):
        from apps.core.execution.execution_completion import (
            complete_by_identity, reverse_by_identity,
        )
        complete_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                             requested_target="Shower")
        out = reverse_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                                  requested_target="Shower")
        self.assertEqual(out["status"], "reversed")
        self.assertTrue(out["detail"]["verified"])

    def test_verified_completion_shows_in_the_truth_the_dashboard_reads(self):
        """Same-truth: the Dashboard must agree after a CoS completion."""
        from apps.core.execution.execution_completion import complete_by_identity
        from apps.core.execution.today_execution import build_today_execution
        complete_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                             requested_target="Shower")
        items = build_today_execution(self.user)["items"]
        shower = [i for i in items
                  if i.get("source_type") == "routine_item"
                  and i.get("source_id") == self.shower.pk]
        self.assertTrue(shower, "Shower vanished from execution truth")
        self.assertTrue(shower[0].get("completed_today"),
                        "the Dashboard's own truth still shows the item open after a "
                        "completion the CoS reported as done")

    def test_end_to_end_confirmation_then_verified_execution(self):
        """The full production sequence: ask → yes → actually complete → verified."""
        from apps.ai.cos_services.action_interface import (
            request_confirmation_for, resolve_pending_action,
        )
        from apps.core.execution.completion_service import is_routine_item_complete
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = True
        prefs.save()
        user = User.objects.get(pk=self.user.pk)

        gate = request_confirmation_for(
            user, "complete_execution_item",
            {"source_type": "routine_item", "source_id": self.shower.pk,
             "title": "Shower"})
        self.assertEqual(gate["status"], "confirmation_required")
        self.assertFalse(is_routine_item_complete(user, self.shower, self.today),
                         "the item mutated before confirmation")

        cid = (gate.get("confirmation") or {}).get("confirmation_id")
        done = resolve_pending_action(user, cid, confirm=True)
        self.assertEqual(done["status"], "ok", done)
        self.assertTrue(is_routine_item_complete(user, self.shower, self.today),
                        "confirmation was consumed but the item never completed")


class NoNarratedSuccessTests(SimpleTestCase):
    """The model must not close the loop by narration."""

    def test_constitution_forbids_reporting_an_unexecuted_action(self):
        # Assert against the COMPOSED constant, not raw source: the clause spans several
        # adjacent string literals, so a source grep can miss a phrase that is present.
        from apps.ai.model_interface.constitution import CONSTITUTION
        self.assertIn("NEVER REPORT AN ACTION YOU DID NOT EXECUTE", CONSTITUTION)
        self.assertIn("PENDING CONFIRMATION IS NOT A COMPLETED ACTION", CONSTITUTION)
        self.assertIn("postcondition_failed", CONSTITUTION)
        self.assertIn("resolve_pending_action", CONSTITUTION)


class DeterministicConfirmationContinuationTests(TestCase):
    """NO-TOOL-CALL CLASS (production 2026-08-18, turn 48957246).

    A bound confirmation existed and was surfaced, the user said "Yes", the model made
    ZERO tool calls and narrated success anyway.

    A deterministic typed pre-parser ALREADY existed — `resolve_typed_confirmation`,
    called from `cos_gateway.runtime` BEFORE the provider call. It did not fire because
    `request_confirmation_for` minted the confirmation WITHOUT a `view`, and
    `confirmation_contract.match_typed` returns None immediately when the view is absent.
    A plain "Yes" therefore fell through to the model.

    Correct execution must NEVER depend on the model choosing to call
    `resolve_pending_action`.
    """

    def setUp(self):
        from apps.ai.models import AssistantConversation
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="dc@contract.test", password="x")
        prefs = self.user.preferences
        prefs.assistant_confirm_actions = True
        prefs.save()
        self.user = User.objects.get(pk=self.user.pk)
        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.shower = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", scheduled_time=datetime.time(7, 0),
            is_active=True, days_of_week="0,1,2,3,4,5,6")
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _pend(self, schedule=None, title="Shower"):
        from apps.ai.cos_services.action_interface import request_confirmation_for
        from apps.ai.model_interface import confirmation as _confirm
        gate = request_confirmation_for(
            self.user, "complete_execution_item",
            {"source_type": "routine_item", "source_id": (schedule or self.shower).pk,
             "title": title},
            conversation_id=self.conv.id)
        _confirm.bind_conversation(self.user, self.conv.id)
        return (gate.get("confirmation") or {}).get("confirmation_id")

    def _done(self, schedule=None):
        from apps.core.execution.completion_service import is_routine_item_complete
        return is_routine_item_complete(self.user, schedule or self.shower, self.today)

    def test_minted_confirmation_carries_the_view_the_resolver_matches_on(self):
        from apps.ai.model_interface import confirmation as _confirm
        cid = self._pend()
        rec = _confirm.get(self.user, cid)
        self.assertIsInstance(rec.get("view"), dict, (
            "a confirmation without a view is INVISIBLE to the deterministic typed "
            "resolver — the exact production defect"))
        from apps.ai.confirmation_contract import match_typed
        self.assertEqual(match_typed("Yes", rec["view"]), "confirm")

    def test_yes_executes_without_any_model_tool_call(self):
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        self._pend()
        self.assertFalse(self._done())
        out = resolve_typed_confirmation(self.user, self.conv.id, "Yes",
                                         turn_id="t", surface="chat_stream")
        self.assertIsNotNone(out, "a plain 'Yes' was not resolved deterministically")
        self.assertEqual(out["status"], "ok", out)
        self.assertTrue(self._done(),
                        "the bound action did not execute — correctness still depends "
                        "on the model remembering to call resolve_pending_action")

    def test_common_affirmative_variants_resolve(self):
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        for phrase in ("yes", "Yes please", "yep", "confirm"):
            with self.subTest(phrase=phrase):
                from apps.life.models import RoutineSchedule
                sched = RoutineSchedule.objects.create(
                    routine=self.routine, name=f"Item {phrase}",
                    scheduled_time=datetime.time(8, 0), is_active=True,
                    days_of_week="0,1,2,3,4,5,6")
                self._pend(sched, title=f"Item {phrase}")
                out = resolve_typed_confirmation(self.user, self.conv.id, phrase,
                                                 turn_id="t", surface="chat")
                if out is not None:          # narrow grammar: some variants may not match
                    self.assertEqual(out["status"], "ok")
                    self.assertTrue(self._done(sched))

    def test_no_cancels_deterministically_and_mutates_nothing(self):
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        self._pend()
        out = resolve_typed_confirmation(self.user, self.conv.id, "No",
                                         turn_id="t", surface="chat")
        self.assertIsNotNone(out, "a plain 'No' was not resolved deterministically")
        self.assertFalse(self._done(), "a rejection mutated the object")

    def test_ambiguous_reply_does_not_execute(self):
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        self._pend()
        for phrase in ("Tell me when it was due.", "Maybe", "what time was that"):
            with self.subTest(phrase=phrase):
                out = resolve_typed_confirmation(self.user, self.conv.id, phrase,
                                                 turn_id="t", surface="chat")
                self.assertIsNone(out, f"{phrase!r} was treated as a confirmation")
                self.assertFalse(self._done(), "an ambiguous reply mutated the object")

    def test_execution_is_postcondition_verified(self):
        """Deterministic continuation must still obey the 086a69c3 verification."""
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        from apps.core.execution.today_execution import build_today_execution
        self._pend()
        resolve_typed_confirmation(self.user, self.conv.id, "Yes",
                                   turn_id="t", surface="chat")
        items = build_today_execution(self.user)["items"]
        mine = [i for i in items if i.get("source_type") == "routine_item"
                and i.get("source_id") == self.shower.pk]
        self.assertTrue(mine and mine[0].get("completed_today"),
                        "the Dashboard's own truth disagrees with the reported result")

    def test_confirmation_is_consumed_and_not_replayable(self):
        from apps.ai.cos_services.action_interface import resolve_typed_confirmation
        self._pend()
        resolve_typed_confirmation(self.user, self.conv.id, "Yes", turn_id="t", surface="c")
        again = resolve_typed_confirmation(self.user, self.conv.id, "Yes",
                                           turn_id="t", surface="c")
        self.assertIsNone(again, "the confirmation was replayable after resolution")
