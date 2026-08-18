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

    def test_executive_lead_exposes_identity_without_prefilling_a_call(self):
        """SUPERSEDED by the 2026-08-18 wrong-target incident.

        This test previously required the lead to PRE-FILL
        `complete_execution_item(source_type=..., source_id=...)` for the current action.
        That is precisely what let "Mark Shower complete" mutate Log Nutrition. The lead
        must point at the identity carried in context — never hand over a ready-to-fire
        call for an object the user has not named.
        """
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        self.assertIn("canonical `source_type` and `source_id`", src,
                      "the model must still know the identity is available")
        self.assertIn("TARGET RULE", src,
                      "the lead must state that a named object outranks the current action")

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


class ExactTargetIntegrityTests(TestCase):
    """WRONG-TARGET MUTATION (2026-08-18, production ToolCallLog bb930a1d).

    "Mark Shower complete" while the current action was Log Nutrition produced:
        complete_execution_item(source_id=19, source_type="routine_item")
        -> recorded "Log Nutrition"

    The model was handed a pre-filled completion call carrying the CURRENT ACTION's
    identity, and fired it for an object the user never named. Nothing in the action
    layer compared the requested target with the resolved one before mutating.

    INVARIANT: requested -> resolved -> mutated must be the SAME canonical object.
    If binding cannot be proven, mutate NOTHING.
    """

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="ti@contract.test", password="x")
        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.shower = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", scheduled_time=datetime.time(7, 0),
            is_active=True, days_of_week="0,1,2,3,4,5,6")
        self.nutrition = RoutineSchedule.objects.create(
            routine=self.routine, name="Log Nutrition",
            scheduled_time=datetime.time(12, 0), is_active=True,
            days_of_week="0,1,2,3,4,5,6")

    def _complete(self, sched):
        from apps.core.execution.completion_service import is_routine_item_complete
        return is_routine_item_complete(self.user, sched, self.today)

    def test_the_exact_production_failure_cannot_recur(self):
        """Shower requested, Log Nutrition's identity supplied → nothing mutates."""
        from apps.core.execution.execution_completion import complete_by_identity
        result = complete_by_identity(
            self.user, "routine_item", self.nutrition.pk, self.today,
            requested_target="Shower")
        self.assertEqual(result["status"], "target_mismatch", result)
        self.assertFalse(result["detail"]["mutated"])
        self.assertFalse(self._complete(self.nutrition),
                         "THE PRODUCTION BUG: an object the user never named was mutated")
        self.assertFalse(self._complete(self.shower))

    def test_mismatch_is_audited_with_both_identities(self):
        from apps.core.execution.execution_completion import complete_by_identity
        result = complete_by_identity(
            self.user, "routine_item", self.nutrition.pk, self.today,
            requested_target="Shower")
        self.assertEqual(result["detail"]["requested_target"], "Shower")
        self.assertEqual(result["detail"]["resolved_target"], "Log Nutrition")
        self.assertFalse(result["detail"]["establishes_absence"])

    def test_matching_target_still_completes(self):
        from apps.core.execution.execution_completion import complete_by_identity
        result = complete_by_identity(
            self.user, "routine_item", self.shower.pk, self.today,
            requested_target="Shower")
        self.assertEqual(result["status"], "recorded")
        self.assertTrue(self._complete(self.shower))
        self.assertFalse(self._complete(self.nutrition),
                         "an unrelated object changed during a correct completion")

    def test_binding_tolerates_harmless_title_variation(self):
        from apps.core.execution.execution_completion import complete_by_identity
        result = complete_by_identity(
            self.user, "routine_item", self.shower.pk, self.today,
            requested_target="shower ")
        self.assertEqual(result["status"], "recorded")

    def test_foreign_object_never_reaches_a_mutation_path(self):
        from apps.core.execution.execution_completion import complete_by_identity
        other = User.objects.create_user(email="ti2@contract.test", password="x")
        result = complete_by_identity(other, "routine_item", self.shower.pk, self.today,
                                      requested_target="Shower")
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(self._complete(self.shower))

    def test_cos_surface_passes_the_requested_target_through(self):
        """The title the model states is used to VERIFY, never to select."""
        from apps.ai.cos_services.execution_completion import complete_execution_item
        out = complete_execution_item(
            self.user, source_type="routine_item", source_id=self.nutrition.pk,
            title="Shower")
        self.assertEqual(out["status"], "target_mismatch")
        self.assertFalse(self._complete(self.nutrition))


class NoCurrentActionSubstitutionTests(SimpleTestCase):
    """The prompt must not hand the model a ready-to-fire call for the current action."""

    def test_executive_lead_does_not_prefill_a_completion_call(self):
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn('complete_execution_item(source_type=\\"', code, (
            "the executive lead pre-fills a completion call with the CURRENT ACTION's "
            "identity. That is what caused Log Nutrition to be completed when the user "
            "asked for Shower."))

    def test_lead_states_that_a_named_object_outranks_the_current_action(self):
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        self.assertIn("TARGET RULE", src)
        self.assertIn("NOT a substitute", src)

    def test_constitution_forbids_substituting_a_write_target(self):
        src = (REPO / "apps/ai/model_interface/constitution.py").read_text(encoding="utf-8")
        self.assertIn("EXACT TARGET INTEGRITY", src)
        for phrase in ("outranks", "change NOTHING", "REVERSE it immediately"):
            self.assertIn(phrase, src)


class VisibleExecutableResolutionTests(TestCase):
    """PRODUCT GATE B — a visible executable item must be addressable even when it is
    NOT the current action (proven gaps: `_facts()` carried no identity, and the routine
    title resolver matched the PARENT ROUTINE's name)."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule
        self.user = User.objects.create_user(email="vb@contract.test", password="x")
        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.shower = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", scheduled_time=datetime.time(7, 0),
            is_active=True, days_of_week="0,1,2,3,4,5,6")

    def test_envelope_carries_identity_for_every_executable_item(self):
        from apps.core.execution.decision_authority import _facts
        projected = _facts({"title": "Shower", "source_type": "routine_item",
                            "source_id": self.shower.pk, "can_complete": True})
        self.assertIn("source_id", projected, (
            "executable items reached the model without canonical identity, so anything "
            "that was not current_action had to be rediscovered by title"))
        self.assertEqual(projected["source_id"], self.shower.pk)
        self.assertTrue(projected["can_complete"])

    def test_routine_resolver_matches_the_item_not_its_parent_routine(self):
        """Production ToolCallLog 2b1093b7 returned `unsupported` because of this."""
        from apps.core.execution.execution_completion import _complete_routine
        out = _complete_routine(self.user, "Shower", self.today)
        self.assertEqual(out["status"], "recorded", (
            "the routine resolver still matches the PARENT ROUTINE's name — 'Shower' "
            f"was compared against '{self.routine.name}'"))


class ReversalIntegrityTests(TestCase):
    """The Constitution promises reversal — prove the CAPABILITY exists and executes."""

    def setUp(self):
        from apps.life.models import Routine, RoutineSchedule, Task
        self.user = User.objects.create_user(email="rv@contract.test", password="x")
        self.today = datetime.date.today()
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Rhythm", time_of_day="morning")
        self.shower = RoutineSchedule.objects.create(
            routine=self.routine, name="Shower", scheduled_time=datetime.time(7, 0),
            is_active=True, days_of_week="0,1,2,3,4,5,6")
        self.nutrition = RoutineSchedule.objects.create(
            routine=self.routine, name="Log Nutrition",
            scheduled_time=datetime.time(12, 0), is_active=True,
            days_of_week="0,1,2,3,4,5,6")
        self.task = Task.objects.create(
            user=self.user, title="Submit the report", due_date=self.today,
            completion_status="pending", status="active")

    def _routine_done(self, sched):
        from apps.core.execution.completion_service import is_routine_item_complete
        return is_routine_item_complete(self.user, sched, self.today)

    def test_the_production_recovery_case(self):
        """CoS completes X → user says "No, don't do that" → X returns to open."""
        from apps.core.execution.execution_completion import (
            complete_by_identity, reverse_by_identity,
        )
        complete_by_identity(self.user, "routine_item", self.nutrition.pk, self.today,
                             requested_target="Log Nutrition")
        self.assertTrue(self._routine_done(self.nutrition))

        out = reverse_by_identity(self.user, "routine_item", self.nutrition.pk,
                                  self.today, requested_target="Log Nutrition")
        self.assertEqual(out["status"], "reversed", out)
        self.assertFalse(self._routine_done(self.nutrition),
                         "the unauthorized completion was not restored")
        self.assertFalse(self._routine_done(self.shower),
                         "reversal changed an unrelated object")

    def test_task_reversal_uses_mark_incomplete(self):
        from apps.core.execution.execution_completion import (
            complete_by_identity, reverse_by_identity,
        )
        complete_by_identity(self.user, "task", self.task.pk, self.today,
                             requested_target="Submit the report")
        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, "completed")
        out = reverse_by_identity(self.user, "task", self.task.pk, self.today,
                                  requested_target="Submit the report")
        self.assertEqual(out["status"], "reversed")
        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, "pending")

    def test_repeated_completion_never_uncompletes(self):
        """Toggle-backed domains must not flip on a second 'complete' request."""
        from apps.core.execution.execution_completion import complete_by_identity
        complete_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                             requested_target="Shower")
        again = complete_by_identity(self.user, "routine_item", self.shower.pk,
                                     self.today, requested_target="Shower")
        self.assertEqual(again["status"], "already_complete")
        self.assertTrue(self._routine_done(self.shower),
                        "a repeated completion silently UNCOMPLETED the item")

    def test_reversal_honours_target_binding(self):
        from apps.core.execution.execution_completion import (
            complete_by_identity, reverse_by_identity,
        )
        complete_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                             requested_target="Shower")
        out = reverse_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                                  requested_target="Log Nutrition")
        self.assertEqual(out["status"], "target_mismatch")
        self.assertTrue(self._routine_done(self.shower), "a mismatched reversal mutated")

    def test_reversing_something_not_complete_mutates_nothing(self):
        from apps.core.execution.execution_completion import reverse_by_identity
        out = reverse_by_identity(self.user, "routine_item", self.shower.pk, self.today,
                                  requested_target="Shower")
        self.assertEqual(out["status"], "not_complete")
        self.assertFalse(out["detail"]["mutated"])

    def test_undo_is_reachable_from_the_cos_surface(self):
        from apps.ai.cos_services.execution_completion import complete_execution_item
        complete_execution_item(self.user, source_type="routine_item",
                                source_id=self.shower.pk, title="Shower")
        out = complete_execution_item(self.user, source_type="routine_item",
                                      source_id=self.shower.pk, title="Shower", undo=True)
        self.assertEqual(out["status"], "reversed")
        self.assertFalse(self._routine_done(self.shower))

    def test_undo_is_exposed_in_the_tool_schema(self):
        from apps.ai.model_interface.constitution import all_tools
        for t in all_tools(writes_enabled=True):
            f = t.get("function") or {}
            if f.get("name") == "complete_execution_item":
                self.assertIn("undo", f["parameters"]["properties"], (
                    "the Constitution instructs the model to reverse, but no undo "
                    "capability is exposed — instruction without capability"))
                return
        self.fail("complete_execution_item is not registered")
