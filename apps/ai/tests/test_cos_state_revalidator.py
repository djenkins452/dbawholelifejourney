"""Tests for CoS mid-response state revalidator — context comparison.

Covers:
1. Snapshot captures completion state correctly
2. Identical snapshots → no change
3. Changed completion → change detected
4. Changed routine count → change detected
5. Changed task count → change detected
6. None snapshot → no change (fail-open)
7. Capture failure → returns None
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.cos_state_revalidator import (
    capture_state_snapshot,
    has_state_changed,
)


def _make_raw(**overrides):
    raw = {
        "prayer_done": False, "bible_done": False,
        "workout_done": False, "journal_done": False,
        "prayer_expected": False, "bible_expected": False,
        "workout_expected": False, "journal_expected": False,
        "routine_done": 0, "routine_total": 5, "tasks_done": 0,
    }
    raw.update(overrides)
    return {
        "faith_summary": "", "routine_summary": "", "task_summary": "",
        "workout_summary": "", "journal_summary": "", "overall_summary": "",
        "next_action": "X", "_raw": raw,
    }


class TestCaptureSnapshot(SimpleTestCase):
    """Snapshot captures the right fields."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_captures_completion_fields(self, mock_facts):
        mock_facts.return_value = _make_raw(
            prayer_done=True, workout_done=False,
            routine_done=3, routine_total=5, tasks_done=2,
        )
        user = MagicMock(); user.id = 1

        snap = capture_state_snapshot(user)

        self.assertIsNotNone(snap)
        self.assertTrue(snap["prayer_done"])
        self.assertFalse(snap["workout_done"])
        self.assertEqual(snap["routine_done"], 3)
        self.assertEqual(snap["tasks_done"], 2)

    def test_capture_failure_returns_none(self):
        user = MagicMock(); user.id = 1
        with patch("apps.ai.cos_fact_statements.build_locked_facts",
                    side_effect=Exception("DB down")):
            snap = capture_state_snapshot(user)
        self.assertIsNone(snap)


class TestHasStateChanged(SimpleTestCase):
    """Pure dict comparison — no LLM text involved."""

    def test_identical_snapshots_no_change(self):
        snap = {
            "prayer_done": False, "bible_done": False,
            "workout_done": False, "journal_done": False,
            "routine_done": 0, "routine_total": 5, "tasks_done": 0,
        }
        self.assertFalse(has_state_changed(snap, dict(snap)))

    def test_prayer_completed_detected(self):
        before = {
            "prayer_done": False, "bible_done": False,
            "workout_done": False, "journal_done": False,
            "routine_done": 0, "routine_total": 5, "tasks_done": 0,
        }
        after = dict(before)
        after["prayer_done"] = True

        self.assertTrue(has_state_changed(before, after))

    def test_routine_count_changed_detected(self):
        before = {
            "prayer_done": False, "bible_done": False,
            "workout_done": False, "journal_done": False,
            "routine_done": 2, "routine_total": 5, "tasks_done": 0,
        }
        after = dict(before)
        after["routine_done"] = 3

        self.assertTrue(has_state_changed(before, after))

    def test_task_count_changed_detected(self):
        before = {
            "prayer_done": False, "bible_done": False,
            "workout_done": False, "journal_done": False,
            "routine_done": 0, "routine_total": 5, "tasks_done": 1,
        }
        after = dict(before)
        after["tasks_done"] = 2

        self.assertTrue(has_state_changed(before, after))

    def test_none_before_no_change(self):
        after = {"prayer_done": True}
        self.assertFalse(has_state_changed(None, after))

    def test_none_after_no_change(self):
        before = {"prayer_done": False}
        self.assertFalse(has_state_changed(before, None))

    def test_both_none_no_change(self):
        self.assertFalse(has_state_changed(None, None))

    def test_multiple_changes_detected(self):
        before = {
            "prayer_done": False, "bible_done": False,
            "workout_done": False, "journal_done": False,
            "routine_done": 0, "routine_total": 5, "tasks_done": 0,
        }
        after = dict(before)
        after["prayer_done"] = True
        after["workout_done"] = True

        self.assertTrue(has_state_changed(before, after))
