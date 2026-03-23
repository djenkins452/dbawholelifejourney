"""Tests for deterministic Day Agenda renderer.

Covers:
1. No items → all sections show "• None"
2. Overdue items correctly detected based on current time
3. Coming up window respected (90 min)
4. Later today contains remaining items
5. Foundation items appear AND still show in correct time bucket
6. No duplication across time buckets
7. Completed items listed individually
8. No aggregation text present
9. Output contains no narrative language
10. Fail-closed returns safe output
11. Chronological ordering in all sections
12. Unified data merge: routines + tasks + calendar
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.ai.beth_day_renderer import (
    COMING_UP_WINDOW_MINUTES,
    _BANNED_WORDS,
    _SAFE_FALLBACK,
    _collect_routine_items,
    _sort_by_time,
    render_day_agenda,
)


def _make_item(name, time_str=None, is_completed=False, importance="flexible"):
    return {
        "item_name": name,
        "scheduled_time": time_str,
        "is_completed": is_completed,
        "importance": importance,
    }


def _make_truth(raw_items=None):
    return {
        "routines": {
            "total": 0, "completed": 0,
            "_raw_items": raw_items or {},
        },
        "domains": {
            "faith": {"prayer_completed": False, "prayer_expected": False,
                      "bible_reading_completed": False, "bible_expected": False},
            "workout": {"completed": False, "expected": False},
            "journal": {"completed": False, "expected": False},
        },
        "tasks": {"completed_today_all": 0},
    }


def _make_locked_facts(next_action="Start with Shower.", **raw_overrides):
    raw = {
        "prayer_done": False, "prayer_expected": False,
        "bible_done": False, "bible_expected": False,
        "workout_done": False, "workout_expected": False,
        "journal_done": False, "journal_expected": False,
        "routine_done": 0, "routine_total": 0, "tasks_done": 0,
    }
    raw.update(raw_overrides)
    return {
        "faith_summary": "", "routine_summary": "", "task_summary": "",
        "workout_summary": "", "journal_summary": "", "overall_summary": "",
        "next_action": next_action, "_raw": raw,
    }


def _fixed_now(hour, minute):
    return timezone.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def _make_normalized_item(name, time_str=None, item_time=None,
                          is_completed=False, is_foundational=False, source="task"):
    """Build a normalized item dict matching the Today Engine format."""
    return {
        "id": f"{source}:{name}",
        "name": name,
        "scheduled_time": item_time,
        "time_str": time_str,
        "completed": is_completed,
        "priority": "foundational" if is_foundational else "flexible",
        "source": source,
    }


# Patch paths for task + calendar collectors (return empty by default)
_P_TASKS = "apps.core.today.today_engine._collect_task_items"
_P_CAL = "apps.core.today.today_engine._collect_calendar_items"


# ---------------------------------------------------------------------------
# Core renderer tests (routine-only, task/calendar mocked empty)
# ---------------------------------------------------------------------------


class TestDayAgendaEmpty(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_empty_state(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_now.return_value = _fixed_now(6, 0)

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Foundation:\n• None", output)
        self.assertIn("Overdue now:\n• None", output)
        self.assertIn("Coming up next:\n• None", output)
        self.assertIn("Later today:\n• None", output)
        self.assertIn("Completed:\n• None", output)


class TestOverdueDetection(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_item(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Shower", "5:30 AM")]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        self.assertIn("Overdue now:\n• Shower (5:30 AM)", output)


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
            "morning": [_make_item("Workout", "6:15 AM")]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        self.assertIn("Coming up next:\n• Workout (6:15 AM)", output)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_outside_window_goes_to_later(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Take Medication", "9:00 AM")]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        self.assertIn("Later today:\n• Take Medication (9:00 AM)", output)

    def test_window_constant(self):
        self.assertEqual(COMING_UP_WINDOW_MINUTES, 90)


class TestFoundationItems(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_foundation_in_both_sections(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Prayer Time", "6:00 AM", importance="foundational")]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        self.assertIn("Foundation:\n• Prayer Time (6:00 AM)", output)


class TestNoDuplication(SimpleTestCase):

    def test_collect_items_no_dupes(self):
        now = _fixed_now(6, 0)
        raw_items = {"morning": [_make_item("Shower", "5:30 AM"), _make_item("Shower", "5:30 AM")]}
        items = _collect_routine_items({"routines": {"_raw_items": raw_items}}, now)
        self.assertEqual(len(items), 2)  # raw collection doesn't dedup

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_duplicate_in_bucket(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Shower", "5:30 AM"), _make_item("Shower", "5:30 AM")]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        overdue_section = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertEqual(overdue_section.count("Shower"), 1)


class TestCompletedItems(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_by_name(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(8, 0)
        mock_facts.return_value = _make_locked_facts(prayer_done=True)
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Shower", "5:30 AM", is_completed=True),
                _make_item("Devotional", "6:00 AM", is_completed=True),
            ]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        self.assertIn("• Shower", output)
        self.assertIn("• Devotional", output)
        self.assertIn("• Prayer", output)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_not_in_time_buckets(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(8, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Shower", "5:30 AM", is_completed=True)]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        overdue_section = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertNotIn("Shower", overdue_section)


class TestNoAggregation(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_banned_words(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts(prayer_done=True, workout_done=True)
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("A", "5:00 AM", is_completed=True),
                _make_item("B", "5:15 AM", is_completed=True),
                _make_item("C", "7:00 AM"),
                _make_item("D", "9:00 AM"),
            ]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        for word in _BANNED_WORDS:
            self.assertNotIn(word, output.lower(), f"Banned word '{word}' found")


class TestNoNarrativeLanguage(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_coaching(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        for word in ["momentum", "solid", "great", "keep it up", "tone",
                      "productive", "focus", "well done"]:
            self.assertNotIn(word, output.lower())


class TestFailClosed(SimpleTestCase):

    def test_fallback_on_error(self):
        user = MagicMock(); user.id = 1
        with patch("apps.ai.cos_fact_statements.build_locked_facts",
                    side_effect=Exception("DB down")):
            output = render_day_agenda(user)
        self.assertEqual(output, _SAFE_FALLBACK)


class TestSections(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_all_sections(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        for section in ["Today", "Foundation:", "Overdue now:", "Coming up next:",
                         "Later today:", "Completed:", "Next:"]:
            self.assertIn(section, output)


# ---------------------------------------------------------------------------
# Chronological ordering tests
# ---------------------------------------------------------------------------


class TestChronologicalOrdering(SimpleTestCase):

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_ordering(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("C", "5:30 AM"), _make_item("A", "5:00 AM"), _make_item("B", "5:15 AM")]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        overdue = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertLess(overdue.index("A (5:00 AM)"), overdue.index("B (5:15 AM)"))
        self.assertLess(overdue.index("B (5:15 AM)"), overdue.index("C (5:30 AM)"))

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_foundation_ordering(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(5, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Later Prayer", "8:00 AM", importance="foundational"),
                _make_item("Early Devotional", "5:30 AM", importance="foundational"),
            ]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        foundation = output.split("Foundation:")[1].split("Overdue")[0]
        self.assertLess(foundation.index("Early Devotional"), foundation.index("Later Prayer"))

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS, return_value=[])
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_items_time_ordered(self, mock_facts, mock_truth, mock_now, _t, _c):
        mock_now.return_value = _fixed_now(10, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Late", "8:00 AM", is_completed=True),
                _make_item("Early", "5:30 AM", is_completed=True),
                _make_item("Mid", "6:45 AM", is_completed=True),
            ]
        })
        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)
        completed = output.split("Completed:")[1].split("Next:")[0]
        self.assertLess(completed.index("Early"), completed.index("Mid"))
        self.assertLess(completed.index("Mid"), completed.index("Late"))

    def test_same_time_stability(self):
        now = _fixed_now(7, 0)
        t = now.replace(hour=6)
        items = [
            {"sort_time": t, "label": "B", "item": {}},
            {"sort_time": t, "label": "A", "item": {}},
        ]
        for _ in range(10):
            result = _sort_by_time(items)
            self.assertEqual(result[0]["label"], "B")  # stable: B first
            self.assertEqual(result[1]["label"], "A")

    def test_sort_helper_ascending(self):
        now = _fixed_now(6, 0)
        items = [
            {"sort_time": now.replace(hour=9), "label": "C", "item": {}},
            {"sort_time": now.replace(hour=5), "label": "A", "item": {}},
            {"sort_time": now.replace(hour=7), "label": "B", "item": {}},
        ]
        result = _sort_by_time(items)
        self.assertEqual([e["label"] for e in result], ["A", "B", "C"])


# ---------------------------------------------------------------------------
# Unified data merge tests (routines + tasks + calendar)
# ---------------------------------------------------------------------------


class TestUnifiedDataMerge(SimpleTestCase):
    """Tasks and calendar events merge with routines into unified buckets."""

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_routine_plus_task_both_appear(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
        """Routine + task → both appear in output."""
        now = _fixed_now(5, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Shower", "5:30 AM")]
        })
        mock_tasks.return_value = [
            _make_normalized_item("Blood work request", "9:00 AM",
                                  item_time=now.replace(hour=9, minute=0), source="task"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Shower (5:30 AM)", output)
        self.assertIn("Blood work request (9:00 AM)", output)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_task(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
        """Task at 5:15 AM when now is 7:00 AM → appears in Overdue."""
        now = _fixed_now(7, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_tasks.return_value = [
            _make_normalized_item("Call doctor", "5:15 AM",
                                  item_time=now.replace(hour=5, minute=15), source="task"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        overdue = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertIn("Call doctor (5:15 AM)", overdue)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_later_includes_task_and_routine(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
        """Both task and routine appear in Later today."""
        now = _fixed_now(5, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Devotional", "9:00 AM")]
        })
        mock_tasks.return_value = [
            _make_normalized_item("Submit report", "10:00 AM",
                                  item_time=now.replace(hour=10, minute=0), source="task"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        later = output.split("Later today:")[1].split("Completed:")[0]
        self.assertIn("Devotional (9:00 AM)", later)
        self.assertIn("Submit report (10:00 AM)", later)

    @patch(_P_CAL)
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_calendar_event_in_coming_up(self, mock_facts, mock_truth, mock_now, mock_tasks, mock_cal):
        """Calendar event within window appears in Coming up."""
        now = _fixed_now(8, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_tasks.return_value = []
        mock_cal.return_value = [
            _make_normalized_item("Team standup", "9:00 AM",
                                  item_time=now.replace(hour=9, minute=0), source="calendar"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        coming = output.split("Coming up next:")[1].split("Later today:")[0]
        self.assertIn("Team standup (9:00 AM)", coming)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_cross_source_duplication(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
        """Same-named item from different sources appears once per bucket."""
        now = _fixed_now(5, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Workout", "6:15 AM")]
        })
        # Task with same name and time
        mock_tasks.return_value = [
            _make_normalized_item("Workout", "6:15 AM",
                                  item_time=now.replace(hour=6, minute=15), source="task"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        coming = output.split("Coming up next:")[1].split("Later today:")[0]
        self.assertEqual(coming.count("Workout"), 1)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_ordering_preserved_after_merge(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
        """All items sorted by time regardless of source."""
        now = _fixed_now(5, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [_make_item("Routine B", "8:00 AM")]
        })
        mock_tasks.return_value = [
            _make_normalized_item("Task A", "7:00 AM",
                                  item_time=now.replace(hour=7), source="task"),
            _make_normalized_item("Task C", "9:00 AM",
                                  item_time=now.replace(hour=9), source="task"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        # All in Later — check ordering
        pos_a = output.index("Task A (7:00 AM)")
        pos_b = output.index("Routine B (8:00 AM)")
        pos_c = output.index("Task C (9:00 AM)")
        self.assertLess(pos_a, pos_b)
        self.assertLess(pos_b, pos_c)

    @patch(_P_CAL, return_value=[])
    @patch(_P_TASKS)
    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_task_in_completed_section(self, mock_facts, mock_truth, mock_now, mock_tasks, _c):
        """Completed task appears in Completed, not time buckets."""
        now = _fixed_now(10, 0)
        mock_now.return_value = now
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_tasks.return_value = [
            _make_normalized_item("Done thing", "8:00 AM",
                                  item_time=now.replace(hour=8), is_completed=True, source="task"),
        ]

        user = MagicMock(); user.id = 1
        output = render_day_agenda(user)

        completed = output.split("Completed:")[1].split("Next:")[0]
        self.assertIn("Done thing", completed)
        overdue = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertNotIn("Done thing", overdue)
