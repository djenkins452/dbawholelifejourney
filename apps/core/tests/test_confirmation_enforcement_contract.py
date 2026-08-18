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
        resolve_pending_action(self.user, cid, confirm=True)
        replay = resolve_pending_action(self.user, cid, confirm=True)
        self.assertNotEqual(replay.get("status"), "ok", "confirmation was replayable")

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
