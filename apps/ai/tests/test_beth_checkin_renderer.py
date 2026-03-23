"""Tests for deterministic check-in renderer + state guard.

Covers:
1. No completed items → shows "• None"
2. Completed items render individually (no aggregation)
3. Upcoming: only time-bound items within window
4. No upcoming → "• None"
5. No grouping text (no "items", "tasks", "routines")
6. Next action always present
7. LLM output containing state language is blocked
8. Fail-closed returns safe output
9. State guard patterns detected correctly
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.ai.beth_checkin_renderer import (
    UPCOMING_WINDOW_MINUTES,
    _BANNED_WORDS,
    _SAFE_FALLBACK,
    _get_completed_items,
    _get_upcoming_items,
    _parse_time_today,
    contains_state_language,
    guard_llm_output,
    render_morning_checkin,
)


def _make_raw(
    prayer_done=False, bible_done=False,
    workout_done=False, journal_done=False,
):
    return {
        "prayer_done": prayer_done,
        "bible_done": bible_done,
        "workout_done": workout_done,
        "journal_done": journal_done,
        "prayer_expected": False,
        "bible_expected": False,
        "workout_expected": False,
        "journal_expected": False,
        "routine_done": 0,
        "routine_total": 0,
        "tasks_done": 0,
    }


def _make_truth(raw_items=None):
    """Build a minimal execution truth dict."""
    return {
        "routines": {
            "total": 0,
            "completed": 0,
            "_raw_items": raw_items or {},
        },
    }


def _make_locked_facts(next_action="Start with Workout.", **raw_overrides):
    raw = _make_raw()
    raw.update(raw_overrides)
    return {
        "faith_summary": "", "routine_summary": "", "task_summary": "",
        "workout_summary": "", "journal_summary": "", "overall_summary": "",
        "next_action": next_action,
        "_raw": raw,
    }


# ---------------------------------------------------------------------------
# Completed items (no aggregation)
# ---------------------------------------------------------------------------


class TestCompletedItems(SimpleTestCase):
    """Completed section shows individual named items, never aggregation."""

    def test_empty_completed(self):
        completed = _get_completed_items(_make_raw(), _make_truth())
        self.assertEqual(completed, [])

    def test_domain_completions_by_name(self):
        raw = _make_raw(prayer_done=True, bible_done=True)
        completed = _get_completed_items(raw, _make_truth())
        self.assertIn("Prayer", completed)
        self.assertIn("Bible reading", completed)

    def test_routine_items_by_name(self):
        """Completed routine items appear by individual name, not as count."""
        raw_items = {
            "morning": [
                {"item_name": "Shower", "is_completed": True},
                {"item_name": "Devotional", "is_completed": True},
                {"item_name": "Workout", "is_completed": False},
            ]
        }
        completed = _get_completed_items(_make_raw(), _make_truth(raw_items))
        self.assertIn("Shower", completed)
        self.assertIn("Devotional", completed)
        self.assertNotIn("Workout", completed)

    def test_no_aggregation_words(self):
        """Output never contains banned aggregation words."""
        raw_items = {
            "morning": [
                {"item_name": "A", "is_completed": True},
                {"item_name": "B", "is_completed": True},
                {"item_name": "C", "is_completed": True},
            ]
        }
        completed = _get_completed_items(_make_raw(), _make_truth(raw_items))
        text = "\n".join(completed)
        for word in _BANNED_WORDS:
            self.assertNotIn(word, text.lower())

    def test_no_duplicate_items(self):
        """Prayer from domain + 'Prayer' routine item = only listed once."""
        raw = _make_raw(prayer_done=True)
        raw_items = {
            "morning": [
                {"item_name": "Prayer", "is_completed": True},
            ]
        }
        completed = _get_completed_items(raw, _make_truth(raw_items))
        self.assertEqual(completed.count("Prayer"), 1)


# ---------------------------------------------------------------------------
# Upcoming items (time-bound only)
# ---------------------------------------------------------------------------


class TestUpcomingItems(SimpleTestCase):
    """Upcoming shows only time-bound items within window."""

    def _make_user_now(self, hour, minute):
        """Create a mock user + fixed 'now' time."""
        now = timezone.now().replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )
        return now

    @patch("apps.core.utils.get_user_now")
    def test_item_within_window_shown(self, mock_now):
        """Item at 6:15 AM shown when now is 5:44 AM (31 min away)."""
        mock_now.return_value = self._make_user_now(5, 44)
        raw_items = {
            "morning": [
                {"item_name": "Workout", "scheduled_time": "6:15 AM",
                 "is_completed": False},
            ]
        }
        user = MagicMock()
        upcoming = _get_upcoming_items(_make_truth(raw_items), user)
        self.assertEqual(len(upcoming), 1)
        self.assertIn("Workout", upcoming[0])
        self.assertIn("6:15 AM", upcoming[0])

    @patch("apps.core.utils.get_user_now")
    def test_item_outside_window_excluded(self, mock_now):
        """Item at 9:00 AM excluded when now is 5:44 AM (196 min away)."""
        mock_now.return_value = self._make_user_now(5, 44)
        raw_items = {
            "morning": [
                {"item_name": "Take Medication", "scheduled_time": "9:00 AM",
                 "is_completed": False},
            ]
        }
        user = MagicMock()
        upcoming = _get_upcoming_items(_make_truth(raw_items), user)
        self.assertEqual(len(upcoming), 0)

    @patch("apps.core.utils.get_user_now")
    def test_completed_item_excluded(self, mock_now):
        """Completed items never show as upcoming."""
        mock_now.return_value = self._make_user_now(5, 44)
        raw_items = {
            "morning": [
                {"item_name": "Prayer", "scheduled_time": "6:00 AM",
                 "is_completed": True},
            ]
        }
        user = MagicMock()
        upcoming = _get_upcoming_items(_make_truth(raw_items), user)
        self.assertEqual(len(upcoming), 0)

    @patch("apps.core.utils.get_user_now")
    def test_no_time_item_excluded(self, mock_now):
        """Items without scheduled_time are never shown."""
        mock_now.return_value = self._make_user_now(5, 44)
        raw_items = {
            "morning": [
                {"item_name": "Journal", "scheduled_time": None,
                 "is_completed": False},
            ]
        }
        user = MagicMock()
        upcoming = _get_upcoming_items(_make_truth(raw_items), user)
        self.assertEqual(len(upcoming), 0)

    @patch("apps.core.utils.get_user_now")
    def test_empty_upcoming_returns_empty_list(self, mock_now):
        """No items → empty list (renderer converts to '• None')."""
        mock_now.return_value = self._make_user_now(5, 44)
        user = MagicMock()
        upcoming = _get_upcoming_items(_make_truth(), user)
        self.assertEqual(upcoming, [])

    def test_upcoming_window_is_90_minutes(self):
        self.assertEqual(UPCOMING_WINDOW_MINUTES, 90)


# ---------------------------------------------------------------------------
# Full renderer output
# ---------------------------------------------------------------------------


class TestFullRendererOutput(SimpleTestCase):
    """Integration tests for the full rendered output."""

    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_aggregation_in_output(self, mock_facts, mock_truth):
        """Full output never contains aggregation words."""
        mock_facts.return_value = _make_locked_facts(
            prayer_done=True, workout_done=True,
        )
        mock_truth.return_value = _make_truth({
            "morning": [
                {"item_name": "Shower", "is_completed": True},
                {"item_name": "Devotional", "is_completed": True},
            ]
        })
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        for word in _BANNED_WORDS:
            self.assertNotIn(word, output.lower(),
                             f"Banned word '{word}' found in output")

    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_empty_state_shows_none(self, mock_facts, mock_truth):
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Completed:\n• None", output)
        self.assertIn("Upcoming:\n• None", output)

    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_next_action_always_present(self, mock_facts, mock_truth):
        mock_facts.return_value = _make_locked_facts(
            next_action="Start with Bible reading.",
        )
        mock_truth.return_value = _make_truth()
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Next: Start with Bible reading.", output)

    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_sections_present(self, mock_facts, mock_truth):
        mock_facts.return_value = _make_locked_facts()
        mock_truth.return_value = _make_truth()
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Morning Check-in", output)
        self.assertIn("Completed:", output)
        self.assertIn("Upcoming:", output)
        self.assertIn("Next:", output)

    @patch("apps.core.execution.execution_truth_engine.get_execution_truth")
    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_coaching_language(self, mock_facts, mock_truth):
        mock_facts.return_value = _make_locked_facts(prayer_done=True)
        mock_truth.return_value = _make_truth()
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        for word in ["solid", "momentum", "great", "keep it up", "tone"]:
            self.assertNotIn(word, output.lower())

    def test_fail_closed_returns_safe_output(self):
        user = MagicMock()
        user.id = 1

        with patch(
            "apps.ai.cos_fact_statements.build_locked_facts",
            side_effect=Exception("DB down"),
        ):
            output = render_morning_checkin(user)

        self.assertEqual(output, _SAFE_FALLBACK)
        self.assertIn("• None", output)


# ---------------------------------------------------------------------------
# Parse time helper
# ---------------------------------------------------------------------------


class TestParseTimeToday(SimpleTestCase):

    def test_parses_am(self):
        now = timezone.now().replace(hour=5, minute=0)
        result = _parse_time_today("6:15 AM", now)
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 6)
        self.assertEqual(result.minute, 15)

    def test_parses_pm(self):
        now = timezone.now().replace(hour=12, minute=0)
        result = _parse_time_today("9:00 PM", now)
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 21)

    def test_invalid_returns_none(self):
        now = timezone.now()
        self.assertIsNone(_parse_time_today("not a time", now))
        self.assertIsNone(_parse_time_today("", now))


# ---------------------------------------------------------------------------
# State guard (unchanged from before)
# ---------------------------------------------------------------------------


class TestContainsStateLanguage(SimpleTestCase):

    def test_detects_you_completed(self):
        self.assertTrue(contains_state_language(
            "You've completed your prayer and Bible reading."
        ))

    def test_detects_momentum_language(self):
        self.assertTrue(contains_state_language(
            "Let's keep the momentum going."
        ))

    def test_detects_solid_tone(self):
        self.assertTrue(contains_state_language(
            "which sets a solid tone for the day"
        ))

    def test_allows_clean_text(self):
        self.assertFalse(contains_state_language(
            "How can I help you today?"
        ))

    def test_empty_text_safe(self):
        self.assertFalse(contains_state_language(""))
        self.assertFalse(contains_state_language(None))


class TestGuardLlmOutput(SimpleTestCase):

    @patch("apps.ai.beth_checkin_renderer.render_checkin_for_time")
    def test_blocks_state_language(self, mock_render):
        mock_render.return_value = "Morning Check-in\n\nCompleted:\n• None"
        user = MagicMock()
        user.id = 1

        result = guard_llm_output(
            "You've completed your prayer. Keep the momentum going!",
            user,
        )
        self.assertEqual(result, "Morning Check-in\n\nCompleted:\n• None")

    def test_allows_clean_output(self):
        user = MagicMock()
        user.id = 1

        clean = "Here's how to set up a new routine in the app."
        result = guard_llm_output(clean, user)
        self.assertEqual(result, clean)

    def test_guard_fallback_on_render_error(self):
        user = MagicMock()
        user.id = 1

        with patch(
            "apps.ai.beth_checkin_renderer.render_checkin_for_time",
            side_effect=Exception("Error"),
        ):
            result = guard_llm_output(
                "You've completed everything today!",
                user,
            )
        self.assertEqual(result, _SAFE_FALLBACK)
