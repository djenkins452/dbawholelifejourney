"""Tests for CoS mid-response state revalidator.

Covers:
1. No correction when response matches current truth
2. Correction appended when item now completed but response says pending
3. No correction when truth says not completed
4. Multiple corrections appended
5. Fail-open: returns original on error
6. No modification of original text (only appends)
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.cos_state_revalidator import revalidate_response


def _make_raw(**overrides):
    raw = {
        "prayer_done": False,
        "bible_done": False,
        "workout_done": False,
        "journal_done": False,
        "prayer_expected": False,
        "bible_expected": False,
        "workout_expected": False,
        "journal_expected": False,
        "routine_done": 0,
        "routine_total": 0,
        "tasks_done": 0,
    }
    raw.update(overrides)
    return {
        "faith_summary": "", "routine_summary": "", "task_summary": "",
        "workout_summary": "", "journal_summary": "", "overall_summary": "",
        "next_action": "X", "_raw": raw,
    }


class TestNoCorrection(SimpleTestCase):
    """Response passes through unchanged when truth matches."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_change_when_truth_matches(self, mock_facts):
        mock_facts.return_value = _make_raw(prayer_done=False)
        user = MagicMock(); user.id = 1

        response = "Prayer is not yet completed. Start with prayer."
        result = revalidate_response(response, user)

        self.assertEqual(result, response)  # No correction needed

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_change_when_response_clean(self, mock_facts):
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        response = "How can I help you today?"
        result = revalidate_response(response, user)

        self.assertEqual(result, response)  # No item referenced


class TestCorrectionAppended(SimpleTestCase):
    """Correction appended when truth changed during generation."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_prayer_now_completed(self, mock_facts):
        """Response says prayer pending, but truth says done → correction."""
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        response = "Prayer is not yet completed."
        result = revalidate_response(response, user)

        self.assertIn("(Update:", result)
        self.assertIn("Prayer", result)
        self.assertIn("has been completed", result)
        # Original text preserved
        self.assertTrue(result.startswith("Prayer is not yet completed."))

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_workout_now_completed(self, mock_facts):
        mock_facts.return_value = _make_raw(workout_done=True)
        user = MagicMock(); user.id = 1

        response = "Your workout is not yet completed."
        result = revalidate_response(response, user)

        self.assertIn("(Update:", result)
        self.assertIn("Workout", result)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_multiple_corrections(self, mock_facts):
        """Multiple items now completed → all listed in correction."""
        mock_facts.return_value = _make_raw(prayer_done=True, workout_done=True)
        user = MagicMock(); user.id = 1

        response = "Prayer is not yet completed. Workout is still pending."
        result = revalidate_response(response, user)

        self.assertIn("(Update:", result)
        self.assertIn("Prayer", result)
        self.assertIn("Workout", result)


class TestNoFalsePositives(SimpleTestCase):
    """No correction when truth hasn't changed."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_correction_when_item_still_pending(self, mock_facts):
        mock_facts.return_value = _make_raw(workout_done=False)
        user = MagicMock(); user.id = 1

        response = "Workout is not yet completed."
        result = revalidate_response(response, user)

        self.assertNotIn("(Update:", result)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_correction_when_item_done_but_not_mentioned_as_pending(self, mock_facts):
        """Item is done and response doesn't say it's pending → no correction."""
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        response = "Great, your prayer is complete. What's next?"
        result = revalidate_response(response, user)

        self.assertNotIn("(Update:", result)


class TestFailOpen(SimpleTestCase):
    """Returns original response if revalidation fails."""

    def test_error_returns_original(self):
        user = MagicMock(); user.id = 1

        with patch("apps.ai.cos_fact_statements.build_locked_facts",
                    side_effect=Exception("DB down")):
            result = revalidate_response("Some response", user)

        self.assertEqual(result, "Some response")

    def test_empty_response_passthrough(self):
        user = MagicMock(); user.id = 1
        self.assertEqual(revalidate_response("", user), "")
        self.assertIsNone(revalidate_response(None, user))


class TestOriginalPreserved(SimpleTestCase):
    """Original LLM text is never modified — only appended to."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_original_text_intact(self, mock_facts):
        mock_facts.return_value = _make_raw(prayer_done=True)
        user = MagicMock(); user.id = 1

        original = "Prayer is not yet completed. Focus on prayer next."
        result = revalidate_response(original, user)

        # Original text must appear at the start, unchanged
        self.assertTrue(result.startswith(original))
        # Correction appended after
        self.assertIn("\n\n(Update:", result)
