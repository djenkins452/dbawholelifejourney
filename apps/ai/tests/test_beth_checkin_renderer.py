"""Tests for deterministic check-in renderer + state guard.

Covers:
1. No completed items → shows "• None"
2. Completed items render correctly
3. Upcoming items list pending expected items
4. Next action always present
5. No extra text (strict format)
6. LLM output containing state language is blocked
7. Fail-closed returns safe output
8. State guard patterns detected correctly
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.beth_checkin_renderer import (
    _SAFE_FALLBACK,
    contains_state_language,
    guard_llm_output,
    render_morning_checkin,
    render_checkin_for_time,
)


def _make_locked_facts(
    prayer_done=False, prayer_expected=False,
    bible_done=False, bible_expected=False,
    workout_done=False, workout_expected=False,
    journal_done=False, journal_expected=False,
    routine_done=0, routine_total=0,
    tasks_done=0, next_action="Start with Workout.",
):
    return {
        "faith_summary": "",
        "routine_summary": "",
        "task_summary": "",
        "workout_summary": "",
        "journal_summary": "",
        "overall_summary": "",
        "next_action": next_action,
        "_raw": {
            "prayer_done": prayer_done,
            "prayer_expected": prayer_expected,
            "bible_done": bible_done,
            "bible_expected": bible_expected,
            "workout_done": workout_done,
            "workout_expected": workout_expected,
            "journal_done": journal_done,
            "journal_expected": journal_expected,
            "routine_done": routine_done,
            "routine_total": routine_total,
            "tasks_done": tasks_done,
        },
    }


class TestRenderMorningCheckin(SimpleTestCase):
    """Test the deterministic morning check-in renderer."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_empty_state_shows_none(self, mock_facts):
        """No completed items → Completed shows '• None'."""
        mock_facts.return_value = _make_locked_facts()
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Completed:", output)
        self.assertIn("• None", output)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_completed_items_listed(self, mock_facts):
        """Completed items are listed by name."""
        mock_facts.return_value = _make_locked_facts(
            prayer_done=True, bible_done=True,
        )
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("• Prayer", output)
        self.assertIn("• Bible reading", output)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_upcoming_shows_pending_expected(self, mock_facts):
        """Upcoming section shows expected but uncompleted items."""
        mock_facts.return_value = _make_locked_facts(
            workout_expected=True, journal_expected=True,
        )
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Upcoming:", output)
        self.assertIn("• Workout", output)
        self.assertIn("• Journal entry", output)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_next_action_always_present(self, mock_facts):
        """Next action line is always present."""
        mock_facts.return_value = _make_locked_facts(
            next_action="Start with Bible reading.",
        )
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Next: Start with Bible reading.", output)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_no_coaching_language(self, mock_facts):
        """Output contains no coaching or commentary."""
        mock_facts.return_value = _make_locked_facts(
            prayer_done=True, workout_expected=True,
        )
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        # Should NOT contain coaching language
        self.assertNotIn("solid", output.lower())
        self.assertNotIn("momentum", output.lower())
        self.assertNotIn("great", output.lower())
        self.assertNotIn("keep it up", output.lower())

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_strict_format_sections(self, mock_facts):
        """Output has exactly the expected sections."""
        mock_facts.return_value = _make_locked_facts()
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("Morning Check-in", output)
        self.assertIn("Completed:", output)
        self.assertIn("Upcoming:", output)
        self.assertIn("Next:", output)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    def test_all_done_shows_all_clear(self, mock_facts):
        """When everything is done, upcoming shows 'All clear'."""
        mock_facts.return_value = _make_locked_facts(
            prayer_done=True, prayer_expected=True,
            bible_done=True, bible_expected=True,
            workout_done=True, workout_expected=True,
            next_action="All items are complete — nothing pending.",
        )
        user = MagicMock()
        user.id = 1

        output = render_morning_checkin(user)

        self.assertIn("• All clear", output)

    def test_fail_closed_returns_safe_output(self):
        """If renderer errors, return safe fallback."""
        user = MagicMock()
        user.id = 1

        # Force an error by mocking build_locked_facts to raise
        with patch(
            "apps.ai.cos_fact_statements.build_locked_facts",
            side_effect=Exception("DB down"),
        ):
            output = render_morning_checkin(user)

        self.assertEqual(output, _SAFE_FALLBACK)
        self.assertIn("Completed:", output)
        self.assertIn("• None", output)


class TestContainsStateLanguage(SimpleTestCase):
    """Test the state language detection."""

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

    def test_detects_still_need(self):
        self.assertTrue(contains_state_language(
            "You still need to complete your workout."
        ))

    def test_allows_clean_text(self):
        self.assertFalse(contains_state_language(
            "How can I help you today?"
        ))

    def test_allows_deterministic_output(self):
        self.assertFalse(contains_state_language(
            "Morning Check-in\n\nCompleted:\n• Prayer\n\nUpcoming:\n• Workout"
        ))

    def test_empty_text_safe(self):
        self.assertFalse(contains_state_language(""))
        self.assertFalse(contains_state_language(None))


class TestGuardLlmOutput(SimpleTestCase):
    """Test the state guard that blocks LLM fabricated state."""

    @patch("apps.ai.beth_checkin_renderer.render_checkin_for_time")
    def test_blocks_state_language(self, mock_render):
        """LLM output with state language is replaced."""
        mock_render.return_value = "Morning Check-in\n\nCompleted:\n• None"
        user = MagicMock()
        user.id = 1

        result = guard_llm_output(
            "You've completed your prayer. Keep the momentum going!",
            user,
        )

        self.assertEqual(result, "Morning Check-in\n\nCompleted:\n• None")

    def test_allows_clean_output(self):
        """LLM output without state language passes through."""
        user = MagicMock()
        user.id = 1

        clean = "Here's how to set up a new routine in the app."
        result = guard_llm_output(clean, user)

        self.assertEqual(result, clean)

    def test_guard_fallback_on_render_error(self):
        """If renderer fails in guard, return safe fallback."""
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
