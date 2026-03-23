"""Tests for deterministic check-in renderer + state guard.

Covers:
1. Check-in output format (Completed / Upcoming / Next sections)
2. Empty state shows "• None"
3. No coaching or aggregation language
4. Fail-closed returns safe output
5. State guard blocks LLM fabricated state
6. Parse time helper
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.ai.beth_checkin_renderer import (
    _SAFE_FALLBACK,
    contains_state_language,
    guard_llm_output,
    render_morning_checkin,
)
from apps.core.today.today_engine import _parse_time_today


def _make_today_context(
    completed=None, coming_up=None, overdue=None,
    later=None, foundation=None, next_action="Start with Shower.",
):
    """Build a minimal Today Engine context for renderer tests."""
    def _entries(items):
        if not items:
            return []
        return [{"sort_time": datetime.max, "label": label, "item": {}} for label in items]

    return {
        "all_items": [],
        "foundation": _entries(foundation),
        "overdue": _entries(overdue),
        "coming_up": _entries(coming_up),
        "later": _entries(later),
        "completed": _entries(completed),
        "next": next_action,
    }


_P_ENGINE = "apps.core.today.today_engine.get_today_context"


class TestCheckinOutput(SimpleTestCase):
    """Check-in renders correctly from Today Engine context."""

    @patch(_P_ENGINE)
    def test_empty_state(self, mock_ctx):
        mock_ctx.return_value = _make_today_context()
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Completed:\n• None", output)
        self.assertIn("Upcoming:\n• None", output)
        self.assertIn("Next:", output)

    @patch(_P_ENGINE)
    def test_completed_items_shown(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(
            completed=["Prayer", "Bible reading"],
        )
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("• Prayer", output)
        self.assertIn("• Bible reading", output)

    @patch(_P_ENGINE)
    def test_upcoming_from_coming_up(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(
            coming_up=["Workout (6:15 AM)"],
        )
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Upcoming:\n• Workout (6:15 AM)", output)

    @patch(_P_ENGINE)
    def test_next_action_shown(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(
            next_action="Start with Bible reading.",
        )
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Next: Start with Bible reading.", output)

    @patch(_P_ENGINE)
    def test_sections_present(self, mock_ctx):
        mock_ctx.return_value = _make_today_context()
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Morning Check-in", output)
        self.assertIn("Completed:", output)
        self.assertIn("Upcoming:", output)
        self.assertIn("Next:", output)

    @patch(_P_ENGINE)
    def test_no_coaching_language(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(completed=["Prayer"])
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        for word in ["solid", "momentum", "great", "keep it up", "tone"]:
            self.assertNotIn(word, output.lower())

    def test_fail_closed(self):
        user = MagicMock(); user.id = 1
        with patch(_P_ENGINE, side_effect=Exception("DB down")):
            output = render_morning_checkin(user)
        self.assertEqual(output, _SAFE_FALLBACK)


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
        self.assertEqual(result.hour, 21)

    def test_invalid_returns_none(self):
        now = timezone.now()
        self.assertIsNone(_parse_time_today("not a time", now))


class TestContainsStateLanguage(SimpleTestCase):

    def test_detects_you_completed(self):
        self.assertTrue(contains_state_language("You've completed your prayer."))

    def test_detects_momentum_language(self):
        self.assertTrue(contains_state_language("Let's keep the momentum going."))

    def test_allows_clean_text(self):
        self.assertFalse(contains_state_language("How can I help you today?"))

    def test_empty_text_safe(self):
        self.assertFalse(contains_state_language(""))
        self.assertFalse(contains_state_language(None))


class TestGuardLlmOutput(SimpleTestCase):

    @patch("apps.ai.beth_checkin_renderer.render_checkin_for_time")
    def test_blocks_state_language(self, mock_render):
        mock_render.return_value = "Morning Check-in\n\nCompleted:\n• None"
        user = MagicMock(); user.id = 1
        result = guard_llm_output("You've completed your prayer.", user)
        self.assertEqual(result, "Morning Check-in\n\nCompleted:\n• None")

    def test_allows_clean_output(self):
        user = MagicMock(); user.id = 1
        clean = "Here's how to set up a new routine."
        self.assertEqual(guard_llm_output(clean, user), clean)

    def test_guard_fallback_on_error(self):
        user = MagicMock(); user.id = 1
        with patch("apps.ai.beth_checkin_renderer.render_checkin_for_time",
                    side_effect=Exception("Error")):
            result = guard_llm_output("You've completed everything!", user)
        self.assertEqual(result, _SAFE_FALLBACK)
