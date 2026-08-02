"""Tests for the canonical action-destination resolver.

Verifies metadata-first routing (rename-safe) for each domain, the keyword
bridge for sub-domain disambiguation, and safe fallback. The critical
rename-safety test proves a renamed item still routes by metadata, not title.
"""

from datetime import time as dtime

from django.conf import settings
from django.test import TestCase

from apps.core.execution.action_routing import resolve_action_destination
from apps.life.models import Routine, RoutineSchedule, Task
from apps.users.models import TermsAcceptance, User


class ActionRoutingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="routing@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _routine_schedule(self, name, activity_type=None):
        routine = Routine.objects.create(user=self.user, name=f"{name} Routine")
        return RoutineSchedule.objects.create(
            routine=routine, name=name, scheduled_time=dtime(6, 0),
            days_of_week="0,1,2,3,4,5,6", is_active=True,
            activity_type=activity_type,
        )

    def _task(self, title, module=""):
        return Task.objects.create(
            user=self.user, title=title, completion_status="pending",
            module=module,
        )

    # ── source_type: meds/supplements → intake (authoritative) ──
    def test_medication_routes_to_intake(self):
        item = {"source_type": "medication_dose", "source_id": 1, "title": "Metformin"}
        self.assertEqual(resolve_action_destination(item), "/health/physical/intake/")

    def test_supplement_routes_to_intake(self):
        item = {"source_type": "supplement_dose", "source_id": 1, "title": "Fish Oil"}
        self.assertEqual(resolve_action_destination(item), "/health/physical/intake/")

    # ── routine activity_type (canonical, rename-safe) → SPECIFIC workflow ──
    def test_workout_routine_routes_to_workout_logging(self):
        sched = self._routine_schedule("Morning Lift", activity_type="workout")
        item = {"source_type": "routine_item", "source_id": sched.pk, "title": "Morning Lift"}
        self.assertEqual(resolve_action_destination(item),
                         "/health/physical/fitness/workout/new/")

    def test_bible_routine_routes_to_faith_workspace(self):
        # Bible Reading opens the Faith workspace — the user goes there to read.
        sched = self._routine_schedule("Morning Scripture", activity_type="bible")
        item = {"source_type": "routine_item", "source_id": sched.pk, "title": "Morning Scripture"}
        self.assertEqual(resolve_action_destination(item), "/faith/")

    def test_journal_routine_routes_to_new_entry(self):
        sched = self._routine_schedule("Evening Pages", activity_type="journal")
        item = {"source_type": "routine_item", "source_id": sched.pk, "title": "Evening Pages"}
        self.assertEqual(resolve_action_destination(item), "/journal/new/")

    def test_household_routine_routes_to_routines(self):
        # No activity_type, household keyword → /life/routines/
        sched = self._routine_schedule("Empty Dishwasher")
        item = {"source_type": "routine_item", "source_id": sched.pk, "title": "Empty Dishwasher"}
        self.assertEqual(resolve_action_destination(item), "/life/routines/")

    def test_generic_routine_defaults_to_routines(self):
        sched = self._routine_schedule("Tidy Desk")
        item = {"source_type": "routine_item", "source_id": sched.pk, "title": "Tidy Desk"}
        self.assertEqual(resolve_action_destination(item), "/life/routines/")

    # ── task → the TASK OBJECT (never a workflow guessed from its title/module) ──
    def test_task_routes_to_the_task_object(self):
        """Rule: an Executive Action card for a task opens THAT task, never a
        workflow inferred from its wording or module."""
        t = self._task("Read Proverbs", module="faith")
        item = {"source_type": "task", "source_id": t.pk, "title": "Read Proverbs", "domain": "faith"}
        self.assertEqual(resolve_action_destination(item), f"/life/tasks/{t.pk}/edit/")

    def test_task_title_substring_does_not_route_to_workflow(self):
        """Regression (2026-07 nav bug): the household task 'Great Backyard …'
        navigated to Nutrition because 'eat' is a SUBSTRING of 'Gr(eat)'. A task
        must open the task; and even the keyword bridge must be word-boundary."""
        t = self._task("Great Backyard Coming to check on lights.")
        item = {"source_type": "task", "source_id": t.pk,
                "title": "Great Backyard Coming to check on lights.", "domain": None}
        dest = resolve_action_destination(item)
        self.assertEqual(dest, f"/life/tasks/{t.pk}/edit/")
        self.assertNotEqual(dest, "/health/physical/nutrition/")

    def test_keyword_bridge_is_word_boundary(self):
        from apps.core.execution.action_routing import _keyword_capability
        # Mid-word false positives must NOT match:
        for title in ("Great backyard", "create a plan", "wheat toast",
                      "have a seat", "theater night"):
            self.assertIsNone(_keyword_capability(title), title)
        # Real word / stem matches still work:
        self.assertEqual(_keyword_capability("eat breakfast"), "log_nutrition")
        self.assertEqual(_keyword_capability("eating dinner"), "log_nutrition")
        self.assertEqual(_keyword_capability("morning run"), "log_workout")

    def test_nutrition_routine_via_keyword_bridge(self):
        # No nutrition activity_type exists; keyword bridge upgrades it.
        sched = self._routine_schedule("Log Nutrition")
        item = {"source_type": "routine_item", "source_id": sched.pk, "title": "Log Nutrition"}
        self.assertEqual(resolve_action_destination(item), "/health/physical/nutrition/")

    # ── rename safety (the headline guarantee) ──
    def test_rename_safe_routing(self):
        """A renamed Bible routine still routes to the Faith workspace because
        resolution keys on activity_type, NOT the title."""
        sched = self._routine_schedule(
            "Completely Unrelated Title", activity_type="bible"
        )
        item = {"source_type": "routine_item", "source_id": sched.pk,
                "title": "Completely Unrelated Title"}
        self.assertEqual(resolve_action_destination(item), "/faith/")

    # ── ACCEPTANCE: routine items route to their WORKFLOW, never Routines ──
    def test_acceptance_routine_workflows(self):
        """The reported bug: routine items navigated to the Routines page. Each
        must route to the workflow its CAPABILITY represents. (activity_type
        only covers workout/journal/bible/faith; the rest resolve via the
        documented title bridge because no activity_type exists for them yet.)"""
        cases = [
            ("Log Nutrition", None,      "/health/physical/nutrition/"),
            ("Journal", "journal",       "/journal/new/"),
            ("Bible Reading", "bible",   "/faith/"),
            ("Prayer Time", "faith",     "/faith/prayers/"),
            ("Measurements", None,       "/health/physical/body-composition/log/"),
            ("Log Workout", None,        "/health/physical/fitness/workout/new/"),
            ("Log Weight", None,         "/health/physical/weight/log/"),
        ]
        for title, activity, expected in cases:
            sched = self._routine_schedule(title, activity_type=activity)
            item = {"source_type": "routine_item", "source_id": sched.pk,
                    "title": title, "activity_type": activity}
            self.assertEqual(
                resolve_action_destination(item), expected,
                f"{title!r} must route to {expected}, not the Routines page.")
            self.assertNotEqual(resolve_action_destination(item), "/life/routines/")

    # ── metadata-driven health anchors are rename-safe ──
    def test_activity_type_makes_health_anchors_rename_safe(self):
        """Once a routine carries a health-anchor activity_type, its workflow is
        rename-safe — the title can become anything and it still routes right."""
        cases = [
            ("weigh_in",         "Unrelated Title 1", "/health/physical/weight/log/"),
            ("nutrition_anchor", "Unrelated Title 2", "/health/physical/nutrition/"),
            ("measurement",      "Unrelated Title 3", "/health/physical/body-composition/log/"),
            ("prayer",           "Unrelated Title 4", "/faith/prayers/"),
        ]
        for activity, title, expected in cases:
            sched = self._routine_schedule(title, activity_type=activity)
            item = {"source_type": "routine_item", "source_id": sched.pk,
                    "title": title, "activity_type": activity}
            self.assertEqual(resolve_action_destination(item), expected,
                             f"activity_type={activity!r} must route to {expected}")

    # ── safe fallback ──
    def test_task_routes_to_task_object_even_when_title_is_opaque(self):
        item = {"source_type": "task", "source_id": 999999, "title": "Mystery thing"}
        self.assertEqual(resolve_action_destination(item), "/life/tasks/999999/edit/")

    def test_task_without_source_id_falls_back_to_task_list(self):
        item = {"source_type": "task", "source_id": None, "title": "Mystery thing"}
        self.assertEqual(resolve_action_destination(item), "/life/tasks/")

    def test_no_dead_link_ever(self):
        # Empty/garbage item → still a real URL, never empty.
        self.assertTrue(resolve_action_destination({}).startswith("/"))
