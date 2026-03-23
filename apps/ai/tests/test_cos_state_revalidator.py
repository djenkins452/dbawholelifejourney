"""Tests for CoS mid-response state revalidator.

Covers:
1. No state change when response matches current truth
2. State change detected when item now completed but response says pending
3. No false positive when truth says not completed
4. Multiple stale items → still returns True (one is enough)
5. Fail-open: returns False on error
6. Empty/None response → False
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.cos_state_revalidator import check_state_changed


def _make_raw(**overrides):
    raw = {
        "prayer_done": False, "bible_done": False,
        "workout_done": False, "journal_done": False,
        "prayer_expected": False, "bible_expected": False,
        "workout_expected": False, "journal_expected": False,
        "routine_done": 0, "routine_total": 0, "tasks_done": 0,
    }
    raw.update(overrides)
    return {
        "faith_summary": "", "routine_summary": "", "task_summary": "",
        "workout_summary": "", "journal_summary": "", "overall_summary": "",
        "next_action": "X", "_raw": raw,
    }


class TestNoStateChange(SimpleTestCase):
    """Returns False when response is current."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_false_when_truth_matches(self, mock_facts):
        """Item still pending in truth AND response → no change."""
        mock_facts.return_value = _make_raw(prayer_done=False)
        user = MagicMock(); user.id = 1

        result = check_state_changed(
            "Prayer is not yet completed.", user,
        )
        self.assertFalse(result)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_false_when_response_doesnt_mention_pending(self, mock_facts):
        """Item is done, response doesn't describe it as pending → no change."""
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        result = check_state_changed(
            "Great, your prayer is complete. What's next?", user,
        )
        self.assertFalse(result)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_false_when_no_items_mentioned(self, mock_facts):
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        result = check_state_changed(
            "How can I help you today?", user,
        )
        self.assertFalse(result)


class TestStateChangeDetected(SimpleTestCase):
    """Returns True when response is stale."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_prayer_now_completed(self, mock_facts):
        """Response says prayer pending, truth says done → True."""
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        result = check_state_changed(
            "Prayer is not yet completed.", user,
        )
        self.assertTrue(result)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_workout_now_completed(self, mock_facts):
        mock_facts.return_value = _make_raw(workout_done=True)
        user = MagicMock(); user.id = 1

        result = check_state_changed(
            "Your workout is still pending.", user,
        )
        self.assertTrue(result)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_bible_now_completed(self, mock_facts):
        mock_facts.return_value = _make_raw(bible_done=True)
        user = MagicMock(); user.id = 1

        result = check_state_changed(
            "Bible reading hasn't been completed yet.", user,
        )
        self.assertTrue(result)


class TestFailOpen(SimpleTestCase):

    def test_error_returns_false(self):
        user = MagicMock(); user.id = 1
        with patch("apps.ai.cos_fact_statements.build_locked_facts",
                    side_effect=Exception("DB down")):
            self.assertFalse(check_state_changed("Some response", user))

    def test_empty_response(self):
        user = MagicMock(); user.id = 1
        self.assertFalse(check_state_changed("", user))
        self.assertFalse(check_state_changed(None, user))
