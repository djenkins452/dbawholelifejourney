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


class TestMergeCorrectness(SimpleTestCase):
    """Routines + tasks both present in all_items."""

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_routine_and_task_merged(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
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

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_past_item_is_overdue(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Shower", "5:30 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        labels = [e["label"] for e in ctx["overdue"]]
        self.assertIn("Shower (5:30 AM)", labels)


class TestComingUpWindow(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_within_window(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_routine_item("Workout", "6:15 AM")]
        })

        ctx = get_today_context(MagicMock(id=1))

        labels = [e["label"] for e in ctx["coming_up"]]
        self.assertIn("Workout (6:15 AM)", labels)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_outside_window_is_later(self, mock_facts, mock_truth, mock_now, _t, _c):
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

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_foundational_items_included(self, mock_facts, mock_truth, mock_now, _t, _c):
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

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_sorted(self, mock_facts, mock_truth, mock_now, _t, _c):
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

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_not_in_overdue(self, mock_facts, mock_truth, mock_now, _t, _c):
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

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_next_from_locked_facts(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts(next_action="Start with Workout.")
        mock_truth.return_value = _make_truth()

        ctx = get_today_context(MagicMock(id=1))

        self.assertEqual(ctx["next"], "Start with Workout.")
