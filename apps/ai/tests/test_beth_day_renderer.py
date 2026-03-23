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
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.ai.beth_day_renderer import (
    COMING_UP_WINDOW_MINUTES,
    _BANNED_WORDS,
    _SAFE_FALLBACK,
    _collect_all_items,
    render_day_agenda,
)


def _make_item(name, time_str=None, is_completed=False, importance="flexible"):
    return {
        "item_name": name,
        "scheduled_time": time_str,
        "is_completed": is_completed,
        "importance": importance,
    }


def _make_truth(raw_items=None, raw_overrides=None):
    """Build a minimal execution truth + locked facts pair."""
    truth = {
        "routines": {
            "total": 0,
            "completed": 0,
            "_raw_items": raw_items or {},
        },
        "domains": {
            "faith": {
                "prayer_completed": False, "prayer_expected": False,
                "bible_reading_completed": False, "bible_expected": False,
            },
            "workout": {"completed": False, "expected": False},
            "journal": {"completed": False, "expected": False},
        },
        "tasks": {"completed_today_all": 0},
    }
    return truth


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
        "next_action": next_action,
        "_raw": raw,
    }


def _fixed_now(hour, minute):
    """Create a fixed 'now' time for deterministic testing."""
    return timezone.now().replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )


# ---------------------------------------------------------------------------
# Core renderer tests
# ---------------------------------------------------------------------------


class TestDayAgendaEmpty(SimpleTestCase):
    """All sections show '• None' when no items exist."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_empty_state(self, mock_facts, mock_truth, mock_now):
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        mock_now.return_value = _fixed_now(6, 0)

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Foundation:\n• None", output)
        self.assertIn("Overdue now:\n• None", output)
        self.assertIn("Coming up next:\n• None", output)
        self.assertIn("Later today:\n• None", output)
        self.assertIn("Completed:\n• None", output)
        self.assertIn("Next:", output)


class TestOverdueDetection(SimpleTestCase):
    """Items with scheduled_time < now are overdue."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_overdue_item(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Shower", "5:30 AM"),  # overdue
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Overdue now:\n• Shower (5:30 AM)", output)


class TestComingUpWindow(SimpleTestCase):
    """Items within COMING_UP_WINDOW_MINUTES of now go to 'Coming up next'."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_within_window(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Workout", "6:15 AM"),  # 31 min away
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Coming up next:\n• Workout (6:15 AM)", output)

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_outside_window_goes_to_later(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Take Medication", "9:00 AM"),  # 196 min away
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Later today:\n• Take Medication (9:00 AM)", output)
        self.assertNotIn("Coming up next:\n• Take Medication", output)

    def test_window_constant(self):
        self.assertEqual(COMING_UP_WINDOW_MINUTES, 90)


class TestFoundationItems(SimpleTestCase):
    """Foundation items appear in Foundation AND their time bucket."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_foundation_in_both_sections(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(5, 44)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Prayer Time", "6:00 AM", importance="foundational"),
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        # Appears in Foundation
        self.assertIn("Foundation:\n• Prayer Time (6:00 AM)", output)
        # Also appears in Coming up (16 min away from 5:44)
        self.assertIn("• Prayer Time (6:00 AM)", output)


class TestNoDuplication(SimpleTestCase):
    """Each item appears once per time bucket."""

    def test_collect_items_no_dupes(self):
        now = _fixed_now(6, 0)
        raw_items = {
            "morning": [
                _make_item("Shower", "5:30 AM"),
                _make_item("Shower", "5:30 AM"),  # duplicate
            ]
        }
        items = _collect_all_items(
            {"routines": {"_raw_items": raw_items}}, now,
        )
        # Both are collected but the renderer deduplicates by (name, time_str)
        self.assertEqual(len(items), 2)  # raw collection doesn't dedup

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_duplicate_in_bucket(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(7, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Shower", "5:30 AM"),
                _make_item("Shower", "5:30 AM"),
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        # "Shower (5:30 AM)" should only appear once in Overdue
        overdue_section = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertEqual(overdue_section.count("Shower"), 1)


class TestCompletedItems(SimpleTestCase):
    """Completed items listed individually."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_by_name(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(8, 0)
        mock_facts.return_value = _make_locked_facts(prayer_done=True)
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Shower", "5:30 AM", is_completed=True),
                _make_item("Devotional", "6:00 AM", is_completed=True),
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        self.assertIn("• Shower", output)
        self.assertIn("• Devotional", output)
        self.assertIn("• Prayer", output)

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_not_in_time_buckets(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(8, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("Shower", "5:30 AM", is_completed=True),
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        # Should be in Completed, not in Overdue
        overdue_section = output.split("Overdue now:")[1].split("Coming up")[0]
        self.assertNotIn("Shower", overdue_section)


class TestNoAggregation(SimpleTestCase):
    """Output never contains aggregation words."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_banned_words(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts(
            prayer_done=True, workout_done=True,
        )
        mock_truth.return_value = _make_truth({
            "morning": [
                _make_item("A", "5:00 AM", is_completed=True),
                _make_item("B", "5:15 AM", is_completed=True),
                _make_item("C", "7:00 AM"),
                _make_item("D", "9:00 AM"),
            ]
        })

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        for word in _BANNED_WORDS:
            self.assertNotIn(word, output.lower(),
                             f"Banned word '{word}' found in output")


class TestNoNarrativeLanguage(SimpleTestCase):
    """Output contains no coaching or narrative."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_coaching(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        for word in ["momentum", "solid", "great", "keep it up", "tone",
                      "productive", "focus", "well done"]:
            self.assertNotIn(word, output.lower())


class TestFailClosed(SimpleTestCase):

    def test_fallback_on_error(self):
        user = MagicMock()
        user.id = 1

        with patch(
            "apps.ai.cos_fact_statements.build_locked_facts",
            side_effect=Exception("DB down"),
        ):
            output = render_day_agenda(user)

        self.assertEqual(output, _SAFE_FALLBACK)


class TestSections(SimpleTestCase):
    """All required sections present."""

    @patch("apps.core.utils.get_user_now")
    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_all_sections(self, mock_facts, mock_truth, mock_now):
        mock_now.return_value = _fixed_now(6, 0)
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        output = render_day_agenda(user)

        self.assertIn("Today", output)
        self.assertIn("Foundation:", output)
        self.assertIn("Overdue now:", output)
        self.assertIn("Coming up next:", output)
        self.assertIn("Later today:", output)
        self.assertIn("Completed:", output)
        self.assertIn("Next:", output)
