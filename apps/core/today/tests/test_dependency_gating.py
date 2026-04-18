"""Tests for Task dependency gating.

Covers the four mandatory cases from the WLJ master prompt:
  1. Dependency hidden — prereq incomplete → dependent absent from all_items,
     every bucket, and next_action.
  2. Dependency released — prereq complete → dependent appears normally.
  3. Independent items unaffected.
  4. Overdue dependency still hidden — scheduled_time passed but prereq
     still incomplete → dependent STILL hidden.

Also covers the shared helper directly: is_task_blocked() decisions for
task/routine/domain prerequisites.
"""

from datetime import date, time

from django.test import TestCase
from django.utils import timezone

from apps.core.execution.dependency_gating import is_task_blocked
from apps.core.today.today_engine import get_today_context
from apps.life.models import Task
from apps.users.models import User


def _make_user(email="dep@example.com"):
    return User.objects.create_user(email=email, password="testpass123")


def _make_task(user, title, **kwargs):
    defaults = dict(
        title=title,
        user=user,
        due_date=timezone.localdate(),
        is_routine=False,
        commitment_level="important",
    )
    defaults.update(kwargs)
    return Task.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Helper unit tests — routing logic
# ---------------------------------------------------------------------------

class TestIsTaskBlockedHelper(TestCase):
    """Unit-test the shared gating rule in isolation."""

    def setUp(self):
        self.user = _make_user("helper@example.com")

    def test_no_depends_on_key_is_not_blocked(self):
        t = _make_task(self.user, "Creatine")
        self.assertFalse(is_task_blocked(t, truth={}))

    def test_hide_until_ready_false_is_not_blocked(self):
        prereq = _make_task(self.user, "Workout")
        t = _make_task(
            self.user, "Protein Shake",
            depends_on_key=f"task:{prereq.pk}",
            hide_until_ready=False,
        )
        self.assertFalse(is_task_blocked(t, truth={}))

    def test_task_prereq_incomplete_blocks(self):
        prereq = _make_task(self.user, "Workout")  # pending
        t = _make_task(
            self.user, "Protein Shake",
            depends_on_key=f"task:{prereq.pk}",
        )
        self.assertTrue(is_task_blocked(t, truth={}))

    def test_task_prereq_complete_releases(self):
        prereq = _make_task(self.user, "Workout")
        prereq.mark_complete()
        t = _make_task(
            self.user, "Protein Shake",
            depends_on_key=f"task:{prereq.pk}",
        )
        self.assertFalse(is_task_blocked(t, truth={}))

    def test_routine_prereq_incomplete_blocks(self):
        t = _make_task(
            self.user, "Protein Shake",
            depends_on_key="routine:42",
        )
        truth = {
            "routines": {
                "_raw_items": {
                    "morning": [
                        {"schedule_id": 42, "is_completed": False,
                         "item_name": "Workout"},
                    ],
                },
            },
            "domains": {},
        }
        self.assertTrue(is_task_blocked(t, truth))

    def test_routine_prereq_complete_releases(self):
        t = _make_task(
            self.user, "Protein Shake",
            depends_on_key="routine:42",
        )
        truth = {
            "routines": {
                "_raw_items": {
                    "morning": [
                        {"schedule_id": 42, "is_completed": True,
                         "item_name": "Workout"},
                    ],
                },
            },
            "domains": {},
        }
        self.assertFalse(is_task_blocked(t, truth))

    def test_domain_prereq_uses_truth_domains(self):
        t = _make_task(
            self.user, "Protein Shake",
            depends_on_key="domain:workout",
        )
        truth_blocked = {"domains": {"workout": {"completed": False}}}
        truth_released = {"domains": {"workout": {"completed": True}}}
        self.assertTrue(is_task_blocked(t, truth_blocked))
        self.assertFalse(is_task_blocked(t, truth_released))

    def test_malformed_key_fails_open(self):
        t = _make_task(self.user, "X", depends_on_key="garbage-no-colon")
        self.assertFalse(is_task_blocked(t, truth={}))

    def test_dangling_task_ref_fails_open(self):
        t = _make_task(
            self.user, "X",
            depends_on_key="task:999999",  # no such task
        )
        self.assertFalse(is_task_blocked(t, truth={}))


# ---------------------------------------------------------------------------
# End-to-end tests — Today Engine output
# ---------------------------------------------------------------------------

class TestTodayEngineGating(TestCase):
    """The four mandatory spec cases, through the real Today Engine."""

    def setUp(self):
        self.user = _make_user("engine@example.com")
        # Force the truth engine to return a stable, empty-routine truth
        # so our assertions are not polluted by real routine data.
        self._truth = {
            "routines": {"total": 0, "completed": 0, "_raw_items": {}},
            "domains": {
                "faith": {"prayer_completed": False, "prayer_expected": False,
                          "bible_reading_completed": False, "bible_expected": False},
                "workout": {"completed": False, "expected": False},
                "journal": {"completed": False, "expected": False},
            },
            "tasks": {"completed_today_all": 0},
            "date": timezone.localdate(),
        }

    def _run(self):
        """Run get_today_context with mocked upstream dependencies."""
        from unittest.mock import patch

        locked_facts = {
            "faith_summary": "", "routine_summary": "", "task_summary": "",
            "workout_summary": "", "journal_summary": "", "overall_summary": "",
            "medication_summary": "", "significant_events_summary": "",
            "next_action": "Start with something generic.",
            "_raw": {
                "prayer_done": False, "bible_done": False,
                "workout_done": False, "journal_done": False,
            },
        }

        with patch(
            "apps.core.execution.execution_truth_engine.get_execution_truth",
            return_value=self._truth,
        ), patch(
            "apps.ai.cos_fact_statements.build_locked_facts",
            return_value=locked_facts,
        ), patch(
            "apps.core.today.today_engine._collect_calendar_items",
            return_value=[],
        ), patch(
            "apps.core.today.today_engine._collect_medication_items",
            return_value=[],
        ):
            return get_today_context(self.user)

    def _names(self, ctx):
        return {i["name"] for i in ctx["all_items"]}

    # ── Case 1: dependency hidden ───────────────────────────────────────
    def test_case1_blocked_task_absent_from_all_items_and_buckets(self):
        workout = _make_task(
            self.user, "Workout",
            scheduled_time=time(6, 0),
            commitment_level="foundational",
        )
        _make_task(
            self.user, "Protein Shake",
            scheduled_time=time(6, 30),
            depends_on_key=f"task:{workout.pk}",
        )

        ctx = self._run()

        self.assertIn("Workout", self._names(ctx))
        self.assertNotIn(
            "Protein Shake", self._names(ctx),
            "Blocked task must not appear in all_items",
        )
        for bucket in ("foundation", "overdue", "coming_up", "later", "completed"):
            labels = [e["label"] for e in ctx[bucket]]
            self.assertFalse(
                any("Protein Shake" in l for l in labels),
                f"Blocked task leaked into bucket '{bucket}': {labels}",
            )
        self.assertNotIn(
            "Protein Shake", ctx["next"],
            "Blocked task name must not appear in next_action",
        )

    # ── Case 2: dependency released ─────────────────────────────────────
    def test_case2_completed_prereq_releases_dependent(self):
        workout = _make_task(
            self.user, "Workout",
            scheduled_time=time(6, 0),
        )
        workout.mark_complete()
        _make_task(
            self.user, "Protein Shake",
            scheduled_time=time(6, 30),
            depends_on_key=f"task:{workout.pk}",
        )

        ctx = self._run()

        self.assertIn(
            "Protein Shake", self._names(ctx),
            "Dependent must appear once prereq is complete",
        )

    # ── Case 3: independent items unaffected ───────────────────────────
    def test_case3_independent_task_unaffected(self):
        _make_task(
            self.user, "Creatine",
            scheduled_time=time(6, 15),
        )

        ctx = self._run()

        self.assertIn("Creatine", self._names(ctx))

    # ── Case 4: overdue dependency still hidden ────────────────────────
    def test_case4_overdue_blocked_still_hidden(self):
        # Workout is NOT complete. Protein shake is scheduled in the past
        # (overdue). It must STILL be hidden — no exceptions.
        workout = _make_task(
            self.user, "Workout",
            scheduled_time=time(5, 0),  # not complete
        )
        _make_task(
            self.user, "Protein Shake",
            scheduled_time=time(0, 1),  # definitively in the past
            depends_on_key=f"task:{workout.pk}",
        )

        ctx = self._run()

        self.assertNotIn(
            "Protein Shake", self._names(ctx),
            "Overdue blocked task must STILL be hidden",
        )
        overdue_labels = [e["label"] for e in ctx["overdue"]]
        self.assertFalse(
            any("Protein Shake" in l for l in overdue_labels),
            "Overdue blocked task leaked into overdue bucket",
        )


# ---------------------------------------------------------------------------
# End-to-end — execution contract (build_today_execution) gating
# ---------------------------------------------------------------------------

class TestExecutionContractGating(TestCase):
    """Blocked tasks must not enter build_today_execution items list — this
    is the feed that powers build_locked_next_action → CoS facts."""

    def setUp(self):
        self.user = _make_user("exec@example.com")

    def test_blocked_task_absent_from_execution_contract(self):
        from unittest.mock import patch
        from apps.core.execution.today_execution import build_today_execution

        workout = _make_task(
            self.user, "Workout",
            scheduled_time=time(6, 0),
        )
        _make_task(
            self.user, "Protein Shake",
            scheduled_time=time(6, 30),
            depends_on_key=f"task:{workout.pk}",
        )

        truth = {
            "routines": {"total": 0, "completed": 0, "_raw_items": {}},
            "domains": {
                "faith": {"prayer_completed": False, "prayer_expected": False,
                          "bible_reading_completed": False, "bible_expected": False},
                "workout": {"completed": False, "expected": False},
                "journal": {"completed": False, "expected": False},
            },
            "tasks": {"completed_today_all": 0},
            "date": timezone.localdate(),
        }

        # Route both the dependency resolution AND the downstream
        # _collect_domain_summaries through the same stubbed truth.
        with patch(
            "apps.core.execution.execution_truth_engine.get_execution_truth",
            return_value=truth,
        ), patch(
            "apps.life.services._routine_internal.get_todays_routine_items",
            return_value={"items_by_window": {}, "routine_completion": {}},
        ), patch(
            "apps.core.ai_state.state_builder.build_medicine_state",
            return_value={"schedule_status_today": []},
        ):
            contract = build_today_execution(self.user)

        titles = {i["title"] for i in contract["items"]}
        self.assertIn("Workout", titles)
        self.assertNotIn(
            "Protein Shake", titles,
            "Blocked task must not enter execution contract — would leak "
            "into next_action / CoS facts",
        )

    def test_completed_prereq_releases_in_execution_contract(self):
        from unittest.mock import patch
        from apps.core.execution.today_execution import build_today_execution

        workout = _make_task(self.user, "Workout", scheduled_time=time(6, 0))
        workout.mark_complete()
        _make_task(
            self.user, "Protein Shake",
            scheduled_time=time(6, 30),
            depends_on_key=f"task:{workout.pk}",
        )

        truth = {
            "routines": {"total": 0, "completed": 0, "_raw_items": {}},
            "domains": {
                "faith": {"prayer_completed": False, "prayer_expected": False,
                          "bible_reading_completed": False, "bible_expected": False},
                "workout": {"completed": False, "expected": False},
                "journal": {"completed": False, "expected": False},
            },
            "tasks": {"completed_today_all": 1},
            "date": timezone.localdate(),
        }

        with patch(
            "apps.core.execution.execution_truth_engine.get_execution_truth",
            return_value=truth,
        ), patch(
            "apps.life.services._routine_internal.get_todays_routine_items",
            return_value={"items_by_window": {}, "routine_completion": {}},
        ), patch(
            "apps.core.ai_state.state_builder.build_medicine_state",
            return_value={"schedule_status_today": []},
        ):
            contract = build_today_execution(self.user)

        titles = {i["title"] for i in contract["items"]}
        self.assertIn("Protein Shake", titles)
