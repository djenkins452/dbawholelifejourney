"""Tests for Today Engine — canonical day context.

Covers:
1. Merge correctness (routines + tasks both present)
2. Overdue detection (past items)
3. Coming up window (90 min)
4. Later items (outside window)
5. Foundation correctness
6. Sorting (all sections chronological)
7. Completed separation (not in overdue)
8. Next action (matches locked)
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.today.today_engine import (
    COMING_UP_WINDOW_MINUTES,
    _collect_routine_items,
    _sort_by_time,
    get_today_context,
)


def _fixed_now(hour, minute):
    return timezone.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def _make_routine_item(name, time_str=None, is_completed=False, importance="flexible"):
    return {
        "item_name": name, "scheduled_time": time_str,
        "is_completed": is_completed, "importance": importance,
        "schedule_id": f"s_{name}",
    }


def _make_truth(raw_items=None):
    return {
        "routines": {"total": 0, "completed": 0, "_raw_items": raw_items or {}},
        "domains": {
            "faith": {"prayer_completed": False, "prayer_expected": False,
                      "bible_reading_completed": False, "bible_expected": False},
            "workout": {"completed": False, "expected": False},
            "journal": {"completed": False, "expected": False},
        },
        "tasks": {"completed_today_all": 0},
    }


def _make_locked_facts(next_action="Start with Shower.", **overrides):
    raw = {
        "prayer_done": False, "prayer_expected": False,
        "bible_done": False, "bible_expected": False,
        "workout_done": False, "workout_expected": False,
        "journal_done": False, "journal_expected": False,
        "routine_done": 0, "routine_total": 0, "tasks_done": 0,
    }
    raw.update(overrides)
    return {
        "faith_summary": "", "routine_summary": "", "task_summary": "",
        "workout_summary": "", "journal_summary": "", "overall_summary": "",
        "next_action": next_action, "_raw": raw,
    }


def _norm_item(name, time_str=None, item_time=None,
               completed=False, priority="flexible", source="task"):
    return {
        "id": f"{source}:{name}", "name": name,
        "scheduled_time": item_time, "time_str": time_str,
        "completed": completed, "priority": priority, "source": source,
    }


_P_TASKS = "apps.core.today.today_engine._collect_task_items"
_P_CAL = "apps.core.today.today_engine._collect_calendar_items"
_P_MEDS = "apps.core.today.today_engine._collect_medication_items"


class TestMergeCorrectness(SimpleTestCase):
    """Routines + tasks both present in all_items."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_routine_and_task_merged(self, mock_facts, mock_truth, mock_now, mock_tasks, _c, _m):
        now = _fixed_now(5, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Shower", "5:30 AM")]
        })
        mock_tasks.return_value = [
            _norm_item("Blood work", "9:00 AM", now.replace(hour=9)),
        ]

        ctx = get_today_context(MagicMock(id=1))

        names = [i["name"] for i in ctx["all_items"]]
        self.assertIn("Shower", names)
        self.assertIn("Blood work", names)


class TestOverdueDetection(SimpleTestCase):

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_past_item_is_overdue(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Shower", "5:30 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        labels = [e["label"] for e in ctx["overdue"]]
        self.assertIn("Shower (5:30 AM)", labels)


class TestComingUpWindow(SimpleTestCase):

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_within_window(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Workout", "6:15 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        labels = [e["label"] for e in ctx["coming_up"]]
        self.assertIn("Workout (6:15 AM)", labels)

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_outside_window_is_later(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Meds", "9:00 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        labels = [e["label"] for e in ctx["later"]]
        self.assertIn("Meds (9:00 AM)", labels)

    def test_window_constant(self):
        self.assertEqual(COMING_UP_WINDOW_MINUTES, 90)


class TestFoundation(SimpleTestCase):

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_foundational_items_included(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(5, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_routine_item("Prayer", "6:00 AM", importance="foundational"),
                _make_routine_item("Shower", "5:30 AM"),
            ]
        })

        ctx = get_today_context(MagicMock(id=1))

        f_labels = [e["label"] for e in ctx["foundation"]]
        self.assertIn("Prayer (6:00 AM)", f_labels)
        self.assertNotIn("Shower (5:30 AM)", f_labels)


class TestSorting(SimpleTestCase):

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_sorted(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_routine_item("C", "5:30 AM"),
                _make_routine_item("A", "5:00 AM"),
                _make_routine_item("B", "5:15 AM"),
            ]
        })

        ctx = get_today_context(MagicMock(id=1))

        labels = [e["label"] for e in ctx["overdue"]]
        self.assertEqual(labels, ["A (5:00 AM)", "B (5:15 AM)", "C (5:30 AM)"])


class TestCompletedSeparation(SimpleTestCase):

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_not_in_overdue(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(8, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Shower", "5:30 AM", is_completed=True)]
        })

        ctx = get_today_context(MagicMock(id=1))

        overdue_labels = [e["label"] for e in ctx["overdue"]]
        completed_labels = [e["label"] for e in ctx["completed"]]
        self.assertNotIn("Shower (5:30 AM)", overdue_labels)
        self.assertIn("Shower (5:30 AM)", completed_labels)


class TestNextAction(SimpleTestCase):

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_next_from_locked_facts(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts(next_action="Start with Workout.")
        mock_truth.return_value = _make_truth()

        ctx = get_today_context(MagicMock(id=1))

        self.assertEqual(ctx["next"], "Start with Workout.")


# ---------------------------------------------------------------------------
# Boundary tests (Foundation filter + Overdue/Coming up time precision)
# ---------------------------------------------------------------------------


class TestFoundationStrictFilter(SimpleTestCase):
    """Only items with priority == 'foundational' appear in Foundation."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_non_foundational_excluded(self, mock_facts, mock_truth, mock_now, mock_tasks, _c, _m):
        mock_now.return_value = _fixed_now(5, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_routine_item("Prayer", "6:00 AM", importance="foundational"),
                _make_routine_item("Shower", "5:30 AM", importance="flexible"),
            ]
        })
        # Task with no foundational flag
        mock_tasks.return_value = [
            _norm_item("Pool work", "8:00 AM",
                       _fixed_now(8, 0), priority="flexible"),
        ]

        ctx = get_today_context(MagicMock(id=1))

        f_labels = [e["label"] for e in ctx["foundation"]]
        self.assertIn("Prayer (6:00 AM)", f_labels)
        self.assertNotIn("Shower (5:30 AM)", f_labels)
        self.assertNotIn("Pool work (8:00 AM)", f_labels)

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_foundational_task_included(self, mock_facts, mock_truth, mock_now, mock_tasks, _c, _m):
        """Tasks explicitly marked foundational DO appear in Foundation."""
        mock_now.return_value = _fixed_now(5, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_tasks.return_value = [
            _norm_item("Critical task", "9:00 AM",
                       _fixed_now(9, 0), priority="foundational"),
        ]

        ctx = get_today_context(MagicMock(id=1))

        f_labels = [e["label"] for e in ctx["foundation"]]
        self.assertIn("Critical task (9:00 AM)", f_labels)


class TestOverdueBoundary(SimpleTestCase):
    """Items at exactly current time are NOT overdue."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_one_minute_before_is_overdue(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """6:59 AM at 7:00 AM → overdue."""
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("A", "6:59 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        self.assertIn("A (6:59 AM)", [e["label"] for e in ctx["overdue"]])

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_exact_time_not_overdue(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """7:00 AM at 7:00 AM → NOT overdue."""
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("A", "7:00 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        self.assertNotIn("A (7:00 AM)", [e["label"] for e in ctx["overdue"]])

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_exact_time_with_seconds_not_overdue(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """7:00 AM at 7:00:45 AM → NOT overdue (seconds normalized)."""
        # Simulate real-world: now has non-zero seconds
        now_with_seconds = _fixed_now(7, 0).replace(second=45)
        mock_now.return_value = now_with_seconds
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("A", "7:00 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        self.assertNotIn("A (7:00 AM)", [e["label"] for e in ctx["overdue"]])


class TestComingUpInclusion(SimpleTestCase):
    """Items at exactly current time appear in Coming up."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_exact_time_in_coming_up(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """7:00 AM at 7:00 AM → coming up."""
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("A", "7:00 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        self.assertIn("A (7:00 AM)", [e["label"] for e in ctx["coming_up"]])

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_15_minutes_later_in_coming_up(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """7:15 AM at 7:00 AM → coming up."""
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("A", "7:15 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        self.assertIn("A (7:15 AM)", [e["label"] for e in ctx["coming_up"]])


# ---------------------------------------------------------------------------
# Medication integration tests
# ---------------------------------------------------------------------------


class TestMedicationItems(SimpleTestCase):
    """Medication items flow through same bucketing as routines/tasks."""

    @patch(_P_MEDS)
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_medication(self, mock_facts, mock_truth, mock_now, _t, _c, mock_meds):
        """Medication past due → appears in overdue."""
        now = _fixed_now(9, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_meds.return_value = [
            _norm_item("Metformin", "8:00 AM", now.replace(hour=8), source="medication"),
        ]

        ctx = get_today_context(MagicMock(id=1))
        labels = [e["label"] for e in ctx["overdue"]]
        self.assertIn("Metformin (8:00 AM)", labels)

    @patch(_P_MEDS)
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_upcoming_medication(self, mock_facts, mock_truth, mock_now, _t, _c, mock_meds):
        """Medication within window → coming up."""
        now = _fixed_now(7, 30)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_meds.return_value = [
            _norm_item("Aspirin", "8:00 AM", now.replace(hour=8), source="medication"),
        ]

        ctx = get_today_context(MagicMock(id=1))
        labels = [e["label"] for e in ctx["coming_up"]]
        self.assertIn("Aspirin (8:00 AM)", labels)

    @patch(_P_MEDS)
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_medication(self, mock_facts, mock_truth, mock_now, _t, _c, mock_meds):
        """Taken medication → completed, not overdue."""
        now = _fixed_now(9, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_meds.return_value = [
            _norm_item("Metformin", "8:00 AM", now.replace(hour=8),
                       completed=True, source="medication"),
        ]

        ctx = get_today_context(MagicMock(id=1))
        completed_labels = [e["label"] for e in ctx["completed"]]
        overdue_labels = [e["label"] for e in ctx["overdue"]]
        self.assertIn("Metformin (8:00 AM)", completed_labels)
        self.assertNotIn("Metformin (8:00 AM)", overdue_labels)

    @patch(_P_MEDS)
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_medication_and_routine_both_appear(self, mock_facts, mock_truth, mock_now, _t, _c, mock_meds):
        """Medication + routine at same time → both appear (no dedup)."""
        now = _fixed_now(5, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Take morning meds", "8:00 AM")]
        })
        mock_meds.return_value = [
            _norm_item("Metformin", "8:00 AM", now.replace(hour=8), source="medication"),
        ]

        ctx = get_today_context(MagicMock(id=1))
        all_names = [i["name"] for i in ctx["all_items"]]
        self.assertIn("Take morning meds", all_names)
        self.assertIn("Metformin", all_names)


class TestDomainCompletionDedup(SimpleTestCase):
    """Case-insensitive dedup for domain completions."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_duplicate_bible_reading(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """'Bible Reading' routine + 'Bible reading' domain → only one."""
        mock_now.return_value = _fixed_now(10, 0)
        mock_facts.return_value = _make_locked_facts(bible_done=True)
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Bible Reading", "5:45 AM", is_completed=True)]
        })

        ctx = get_today_context(MagicMock(id=1))
        completed_names = [e["label"] for e in ctx["completed"]]
        # Count entries containing "bible" (case insensitive)
        bible_count = sum(1 for n in completed_names if "bible" in n.lower())
        self.assertEqual(bible_count, 1)


class TestFoundationIncludesCompleted(SimpleTestCase):
    """Foundation shows only INCOMPLETE foundational items."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_foundational_not_in_foundation(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """Completed foundational item does NOT appear in Foundation."""
        mock_now.return_value = _fixed_now(10, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_routine_item("Prayer", "5:30 AM", is_completed=True, importance="foundational"),
                _make_routine_item("Shower", "6:00 AM", is_completed=False, importance="foundational"),
            ]
        })

        ctx = get_today_context(MagicMock(id=1))

        f_labels = [e["label"] for e in ctx["foundation"]]
        self.assertNotIn("Prayer (5:30 AM)", f_labels)  # completed → only in Completed
        self.assertIn("Shower (6:00 AM)", f_labels)       # incomplete → in Foundation
        self.assertEqual(len(f_labels), 1)

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_foundational_only_in_completed(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """Completed foundational appears ONLY in Completed, not Foundation."""
        mock_now.return_value = _fixed_now(10, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_routine_item("Prayer", "5:30 AM", is_completed=True, importance="foundational"),
            ]
        })

        ctx = get_today_context(MagicMock(id=1))

        f_labels = [e["label"] for e in ctx["foundation"]]
        c_labels = [e["label"] for e in ctx["completed"]]
        self.assertNotIn("Prayer (5:30 AM)", f_labels)
        self.assertIn("Prayer (5:30 AM)", c_labels)


class TestDomainDedupWithRoutine(SimpleTestCase):
    """Domain completions suppressed when routine covers same domain."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_prayer_routine_suppresses_domain(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """'Prayer Time' routine exists → 'Prayer' domain NOT added."""
        mock_now.return_value = _fixed_now(10, 0)
        mock_facts.return_value = _make_locked_facts(prayer_done=True)
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Prayer Time", "5:30 AM", is_completed=True)]
        })

        ctx = get_today_context(MagicMock(id=1))

        all_names = [i["name"] for i in ctx["all_items"]]
        self.assertIn("Prayer Time", all_names)
        self.assertNotIn("Prayer", all_names)  # domain suppressed

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_domain_added_when_no_routine(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """No prayer routine → 'Prayer' domain IS added."""
        mock_now.return_value = _fixed_now(10, 0)
        mock_facts.return_value = _make_locked_facts(prayer_done=True)
        mock_truth.return_value = _make_truth()  # no routine items

        ctx = get_today_context(MagicMock(id=1))

        all_names = [i["name"] for i in ctx["all_items"]]
        self.assertIn("Prayer", all_names)  # domain added since no routine


class TestNextActionOverduePriority(SimpleTestCase):
    """Overdue items must take precedence over locked-next-action."""

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_item_becomes_next(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """When items are overdue, next should point to the first overdue item."""
        now = _fixed_now(9, 30)
        mock_now.return_value = now
        # Locked facts says "Evening Medications" but meds are overdue
        mock_facts.return_value = _make_locked_facts(
            next_action="Start with Evening Medications.",
        )
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_routine_item("Prayer", "5:30 AM", is_completed=True),
            ],
        })

        # Add an overdue medication via the meds mock
        # We need to make the overdue item appear in the overdue bucket
        # The Today Engine collects from truth + tasks + meds
        # Since we're testing the next-action override, let's use tasks
        # to create an overdue item
        with patch(_P_TASKS) as mock_tasks_inner:
            mock_tasks_inner.return_value = [
                _norm_item(
                    "Atorvastatin", "9:00 AM",
                    now.replace(hour=9, minute=0),
                    priority="important", source="medication",
                ),
            ]

            ctx = get_today_context(MagicMock(id=1))

        # The overdue medication should be "next", not "Evening Medications"
        self.assertIn("Atorvastatin", ctx["next"])
        self.assertNotIn("Evening", ctx["next"])

    @patch(_P_MEDS, return_value=[])
    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_overdue_uses_locked_facts(self, mock_facts, mock_truth, mock_now, _t, _c, _m):
        """When nothing is overdue, next comes from locked facts as before."""
        mock_now.return_value = _fixed_now(5, 0)
        mock_facts.return_value = _make_locked_facts(
            next_action="Start with Workout.",
        )
        mock_truth.return_value = _make_truth()

        ctx = get_today_context(MagicMock(id=1))

        self.assertEqual(ctx["next"], "Start with Workout.")
