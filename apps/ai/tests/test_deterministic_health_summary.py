# ==============================================================================
# Tests for apps/ai/deterministic_health_summary.py
# ==============================================================================
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.ai.deterministic_health_summary import (
    build_health_summary_response,
    is_health_summary_query,
)


class IsHealthSummaryQueryTests(TestCase):
    """Tests for the lexical health-summary detection function."""

    # ── Should match ────────────────────────────────────────────

    def test_direct_health_question(self):
        self.assertTrue(
            is_health_summary_query("How's my health?")
        )

    def test_health_status_request(self):
        self.assertTrue(
            is_health_summary_query("Give me my health status")
        )

    def test_overall_health_with_context(self):
        """The exact message from the reported incident."""
        self.assertTrue(
            is_health_summary_query(
                "I have been working hard on my health, how have I been doing overall?"
            )
        )

    def test_how_am_i_doing_with_health_keyword(self):
        self.assertTrue(
            is_health_summary_query("how am I doing with my health?")
        )

    def test_my_stats(self):
        self.assertTrue(
            is_health_summary_query("show me my stats")
        )

    def test_my_numbers(self):
        self.assertTrue(
            is_health_summary_query("what are my numbers?")
        )

    def test_health_snapshot(self):
        self.assertTrue(
            is_health_summary_query("health snapshot")
        )

    def test_wellness_summary(self):
        self.assertTrue(
            is_health_summary_query("give me a wellness summary")
        )

    def test_my_fitness(self):
        self.assertTrue(
            is_health_summary_query("how's my fitness?")
        )

    def test_health_overview(self):
        self.assertTrue(
            is_health_summary_query("health overview please")
        )

    def test_progress_with_weight(self):
        self.assertTrue(
            is_health_summary_query("what's my progress on weight?")
        )

    def test_how_have_i_been_with_workouts(self):
        self.assertTrue(
            is_health_summary_query("how have I been doing with my workouts?")
        )

    # ── Should NOT match ────────────────────────────────────────

    def test_general_checkin_no_health(self):
        """General check-in without health keywords → should NOT match."""
        self.assertFalse(
            is_health_summary_query("how am I doing today?")
        )

    def test_task_question(self):
        self.assertFalse(
            is_health_summary_query("what tasks do I have left?")
        )

    def test_simple_greeting(self):
        self.assertFalse(
            is_health_summary_query("good morning")
        )

    def test_journal_question(self):
        self.assertFalse(
            is_health_summary_query("what should I journal about?")
        )

    def test_log_weight_intent(self):
        """Logging data is NOT a summary query."""
        self.assertFalse(
            is_health_summary_query("log my weight at 300 lbs")
        )

    def test_empty_message(self):
        self.assertFalse(is_health_summary_query(""))

    def test_none_message(self):
        self.assertFalse(is_health_summary_query(None))

    def test_overall_without_health(self):
        """'overall' alone without health keywords should not match."""
        self.assertFalse(
            is_health_summary_query("how have I been doing overall?")
        )

    def test_how_have_i_been_without_health(self):
        """Bare 'how have I been' without health words → should not match."""
        self.assertFalse(
            is_health_summary_query("how have I been?")
        )


class BuildHealthSummaryResponseTests(TestCase):
    """Tests for the deterministic health summary builder."""

    def _mock_health_state(self):
        """Return a realistic health state dict."""
        return {
            'weight_current': 302.9,
            'weight_unit': 'lb',
            'weight_trend': 'decreasing',
            'weight_goal': 250.0,
            'weight_goal_unit': 'lb',
            'weight_goal_remaining': 52.9,
            'weight_goal_on_track': True,
            'sleep_avg_duration_7d': 414.0,  # ~6.9 hours
            'sleep_trend': 'stable',
            'steps_avg_7d': 8500,
            'glucose_avg_7d': 123,
            'heart_rate_avg_7d': 72,
            'bp_systolic': 128,
            'bp_diastolic': 82,
            'blood_oxygen_avg_7d': 97.5,
        }

    def _mock_fitness_state(self):
        """Return a realistic fitness state dict."""
        return {
            'workouts_7d': 16,
            'workout_minutes_7d': 480,
        }

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_builds_complete_summary(self, mock_gms):
        """With full data, response includes all metrics."""
        mock_gms.side_effect = lambda user, module: {
            'health': self._mock_health_state(),
            'fitness': self._mock_fitness_state(),
            'medication': {'adherence_pct_7d': 95.0},
        }.get(module, {})

        user = MagicMock()
        result = build_health_summary_response(user)

        self.assertIsNotNone(result)
        self.assertIn('302.9 lbs', result)
        self.assertIn('trending down', result)
        self.assertIn('16 sessions', result)
        self.assertIn('6.9 hrs', result)
        self.assertIn('123 mg/dL', result)
        self.assertIn('72 bpm', result)
        self.assertIn('128/82', result)
        self.assertIn('8,500', result)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_includes_weight_goal(self, mock_gms):
        mock_gms.side_effect = lambda user, module: {
            'health': self._mock_health_state(),
            'fitness': self._mock_fitness_state(),
        }.get(module, {})

        user = MagicMock()
        result = build_health_summary_response(user)

        self.assertIn('250 lbs', result)
        self.assertIn('52.9 lbs to go', result)
        self.assertIn('on track', result)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_none_with_no_data(self, mock_gms):
        """No health or fitness data → returns None (falls through to LLM)."""
        mock_gms.return_value = {}

        user = MagicMock()
        result = build_health_summary_response(user)
        self.assertIsNone(result)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_partial_data_still_works(self, mock_gms):
        """Only weight data → still produces a response."""
        mock_gms.side_effect = lambda user, module: {
            'health': {'weight_current': 302.9, 'weight_unit': 'lb', 'weight_trend': 'decreasing'},
            'fitness': {},
        }.get(module, {})

        user = MagicMock()
        result = build_health_summary_response(user)

        self.assertIsNotNone(result)
        self.assertIn('302.9 lbs', result)
        self.assertIn('trending down', result)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_encouragement_workout_and_weight(self, mock_gms):
        """Weight trending down + 3+ workouts → specific encouragement."""
        mock_gms.side_effect = lambda user, module: {
            'health': {'weight_current': 300, 'weight_unit': 'lb', 'weight_trend': 'decreasing'},
            'fitness': {'workouts_7d': 4},
        }.get(module, {})

        user = MagicMock()
        result = build_health_summary_response(user)
        self.assertIn("putting in the work", result)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_exception_returns_none(self, mock_gms):
        """On exception, returns None to fall through to LLM gracefully."""
        mock_gms.side_effect = Exception("DB connection lost")

        user = MagicMock()
        result = build_health_summary_response(user)
        self.assertIsNone(result)
