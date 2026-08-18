# ==============================================================================
# File: apps/core/tests/test_execution_completion_identity_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Identity-first execution completion contract (2026-08-18 incident)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""Regression contract for the "Mark Shower complete" production incident.

WHAT HAPPENED: the Dashboard showed Shower as the current executable action with a
Mark Complete control. The user said "Mark Shower complete". The CoS called
`complete_task`, which only searches Tasks — Shower is a `routine_item` — and the miss
message ("I couldn't find an incomplete task matching 'Shower'") was generalized by the
model into "you might not have a scheduled routine item matching that" and "it might not
be listed as an incomplete task for today", contradicting the screen.

TWO defects, guarded separately:
  1. identity was delivered but the completion verb could not accept it
  2. a type-scoped resolver miss was reported as global absence

These tests cover the CLASS across executable types, not the word "Shower".
"""

import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.execution.execution_completion import (
    SOURCE_TYPE_TO_KIND,
    complete_by_identity,
    kind_for_source_type,
)

User = get_user_model()
REPO = Path(__file__).resolve().parents[3]


class VocabularyBridgeTests(SimpleTestCase):
    """ONE deterministic mapping; unsupported types fail closed."""

    def test_every_executable_source_type_maps_to_a_completion_kind(self):
        # The executable source types produced by build_today_execution.
        for source_type in ("task", "routine_item", "medication_dose", "supplement_dose"):
            with self.subTest(source_type=source_type):
                self.assertIsNotNone(kind_for_source_type(source_type),
                                     f"{source_type} is surfaced as executable but has no "
                                     "completion route — the CoS cannot act on it")

    def test_unsupported_source_type_fails_closed(self):
        self.assertIsNone(kind_for_source_type("journal_entry"))
        self.assertIsNone(kind_for_source_type(""))
        self.assertIsNone(kind_for_source_type(None))

    def test_mapping_lives_in_exactly_one_place(self):
        """No scattered translations across handlers or prompts."""
        hits = []
        for path in REPO.glob("apps/**/*.py"):
            rel = str(path.relative_to(REPO))
            if "execution_completion.py" in rel or "/tests" in rel:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if '"routine_item": "routine"' in text or "'routine_item': 'routine'" in text:
                hits.append(rel)
        self.assertEqual(hits, [], f"duplicate vocabulary mapping found in {hits}")


class RoutineIdentityCompletionTests(TestCase):
    """The direct acceptance case: complete the exact routine occurrence by identity."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="ec1@contract.test", password="x")
        self.other = User.objects.create_user(email="ec1b@contract.test", password="x")
        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", days_of_week="0,1,2,3,4,5,6",
            scheduled_time=datetime.time(7, 0), is_active=True)

    def test_completes_the_exact_occurrence_by_identity(self):
        from apps.core.execution.completion_service import is_routine_item_complete
        result = complete_by_identity(self.user, "routine_item", self.schedule.pk, self.today)
        self.assertEqual(result["status"], "recorded", result)
        self.assertEqual(result["detail"]["source_id"], self.schedule.pk)
        self.assertTrue(is_routine_item_complete(self.user, self.schedule, self.today),
                        "the exact occurrence was not marked complete")

    def test_uses_the_same_authority_as_the_dashboard_control(self):
        """Dashboard posts to routine_schedule_toggle → toggle_routine_completion."""
        from unittest import mock
        with mock.patch("apps.life.services.routine_helpers.toggle_routine_completion") as m:
            complete_by_identity(self.user, "routine_item", self.schedule.pk, self.today)
            self.assertTrue(m.called,
                            "routine completion must delegate to toggle_routine_completion "
                            "— the exact authority the Dashboard button uses")
            called_schedule = m.call_args[0][1]
            self.assertEqual(called_schedule.pk, self.schedule.pk)

    def test_already_complete_is_idempotent(self):
        complete_by_identity(self.user, "routine_item", self.schedule.pk, self.today)
        again = complete_by_identity(self.user, "routine_item", self.schedule.pk, self.today)
        self.assertEqual(again["status"], "already_complete")

    def test_foreign_user_identity_mutates_nothing(self):
        from apps.core.execution.completion_service import is_routine_item_complete
        result = complete_by_identity(self.other, "routine_item", self.schedule.pk, self.today)
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(is_routine_item_complete(self.user, self.schedule, self.today),
                         "a foreign user's request completed someone else's occurrence")

    def test_invalid_identity_mutates_nothing(self):
        result = complete_by_identity(self.user, "routine_item", 999999999, self.today)
        self.assertEqual(result["status"], "not_found")
        self.assertTrue(result["detail"]["establishes_absence"],
                        "a genuinely missing id DOES establish absence")


class TaskIdentityCompletionTests(TestCase):
    """Task keeps its existing canonical authority; identity path is explicit."""

    def setUp(self):
        from apps.life.models import Task
        self.user = User.objects.create_user(email="ec2@contract.test", password="x")
        self.today = datetime.date.today()
        self.task = Task.objects.create(
            user=self.user, title="Submit the report", due_date=self.today,
            completion_status="pending", status="active")

    def test_completes_by_identity_via_mark_complete(self):
        result = complete_by_identity(self.user, "task", self.task.pk, self.today)
        self.assertEqual(result["status"], "recorded", result)
        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, "completed")

    def test_foreign_task_mutates_nothing(self):
        other = User.objects.create_user(email="ec2b@contract.test", password="x")
        result = complete_by_identity(other, "task", self.task.pk, self.today)
        self.assertEqual(result["status"], "not_found")
        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, "pending")


class DoseAuthorityConvergenceTests(SimpleTestCase):
    """Dashboard and CoS must complete a dose through ONE shared service."""

    def test_shared_dose_service_exists(self):
        from apps.health.services.dose_completion import complete_dose, is_dose_complete
        self.assertTrue(callable(complete_dose))
        self.assertTrue(callable(is_dose_complete))

    def test_dashboard_view_delegates_to_the_shared_service(self):
        src = (REPO / "apps/dashboard_v2/views.py").read_text(encoding="utf-8")
        self.assertIn("from apps.health.services.dose_completion import", src,
                      "the Dashboard dose control must use the shared authority")

    def test_dashboard_no_longer_inlines_dose_completion(self):
        src = (REPO / "apps/dashboard_v2/views.py").read_text(encoding="utf-8")
        self.assertNotIn('log.mark_taken(source=IntakeLog.SOURCE_UI_PER_ITEM)', src,
                         "inline dose-completion logic is back in the view — the UI and the "
                         "CoS would diverge again")

    def test_cos_dose_path_uses_the_same_service(self):
        src = (REPO / "apps/core/execution/execution_completion.py").read_text(encoding="utf-8")
        self.assertIn("from apps.health.services.dose_completion import complete_dose", src)


class TemporalSemanticsTests(TestCase):
    """Current-action identity must not inherit the retrospective 'yesterday' default."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="ec3@contract.test", password="x")
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", days_of_week="0,1,2,3,4,5,6",
            scheduled_time=datetime.time(7, 0), is_active=True)

    def test_identity_path_defaults_to_today_not_yesterday(self):
        from apps.ai.cos_services.execution_completion import complete_execution_item
        from apps.core.utils import get_user_today
        today = get_user_today(self.user) or datetime.date.today()
        out = complete_execution_item(
            self.user, source_type="routine_item", source_id=self.schedule.pk)
        self.assertEqual(out["day"], today.isoformat(),
                         "a CURRENT action was completed against the wrong day — the "
                         "retrospective 'yesterday' default leaked into current execution")

    def test_legacy_title_path_keeps_its_retrospective_default(self):
        """The get_execution_review reconciliation flow must not change behaviour."""
        from apps.ai.cos_services.execution_completion import complete_execution_item
        from apps.core.utils import get_user_today
        today = get_user_today(self.user) or datetime.date.today()
        out = complete_execution_item(self.user, kind="routine", title="Shower")
        self.assertEqual(out["day"], (today - datetime.timedelta(days=1)).isoformat(),
                         "legacy kind+title path lost its retrospective default")


class ResultGroundingContractTests(TestCase):
    """A type-scoped miss must never read as global absence."""

    def setUp(self):
        self.user = User.objects.create_user(email="ec4@contract.test", password="x")

    def test_complete_task_miss_does_not_establish_absence(self):
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)
        result = handler.handle_complete_task(task_keyword="Shower")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "task_type_no_match",
                         "the miss must be typed, not a generic not-found")
        self.assertIsNotNone(result.data, "the failure carries no structured evidence")
        self.assertFalse(result.data["establishes_absence"], (
            "a Task-only miss claimed to establish that the object is absent from WLJ. "
            "This is the field that stops the CoS contradicting the screen."))
        self.assertEqual(result.data["searched_type"], "task")
        self.assertIn("complete_execution_item", result.data["retry_with"])

    def test_miss_message_scopes_itself_to_tasks(self):
        from apps.ai.action_handlers import ActionHandler
        result = ActionHandler(self.user).handle_complete_task(task_keyword="Shower")
        lowered = result.message.lower()
        self.assertIn("tasks", lowered)
        for forbidden in ("not scheduled", "isn't scheduled", "already done",
                          "does not exist", "doesn't exist"):
            self.assertNotIn(forbidden, lowered,
                             f"the Task-scoped miss asserts {forbidden!r} about reality")

    def test_evidence_reaches_the_model_facing_result(self):
        from apps.ai.cos_services import action_interface
        out = action_interface.request_action(
            self.user, "complete_task", {"task_keyword": "Shower"},
            turn_id="t", surface="test")
        if out.get("status") == "error" and "evidence" in out:
            self.assertFalse(out["evidence"]["establishes_absence"])
        else:
            self.assertIn(out.get("status"), ("error", "ok", "confirmation_required"))


class GroundingInvariantTests(SimpleTestCase):
    """The model must be told that a failed action cannot overturn established truth."""

    def test_constitution_forbids_contradicting_established_truth(self):
        src = (REPO / "apps/ai/model_interface/constitution.py").read_text(encoding="utf-8")
        self.assertIn("NEVER OVERTURNS ESTABLISHED TRUTH", src)
        self.assertIn("establishes_absence", src,
                      "the grounding clause must reference the structured evidence field")

    def test_no_shower_special_case_anywhere(self):
        for rel in ("apps/ai/model_interface/constitution.py",
                    "apps/ai/model_interface/service.py",
                    "apps/core/execution/execution_completion.py",
                    "apps/ai/action_handlers.py"):
            src = (REPO / rel).read_text(encoding="utf-8")
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("#"))
            self.assertNotIn("Shower", code, f"{rel} special-cases Shower")


class ExecutableIdentityDeliveryTests(SimpleTestCase):
    """Identity must be visible to the model, not merely present in the data."""

    def test_executive_lead_names_the_identity_call(self):
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        self.assertIn("complete_execution_item(source_type=", src,
                      "the current action must tell the model how to complete it by identity")

    def test_action_carries_source_id(self):
        src = (REPO / "apps/core/decision_engine/action_prioritizer.py").read_text(
            encoding="utf-8")
        self.assertIn("a['source_id'] = meta.get('source_id')",
                      src.replace('"', "'"),
                      "the action must carry canonical occurrence identity")

    def test_no_second_completion_intent_was_added(self):
        from apps.ai.model_interface.constitution import ALLOWED_WRITE_INTENTS
        for banned in ("complete_routine_item", "complete_dose", "complete_execution"):
            self.assertNotIn(banned, ALLOWED_WRITE_INTENTS,
                             f"{banned} is a SECOND completion verb — extend the existing one")
