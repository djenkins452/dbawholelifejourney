# ==============================================================================
# Tests for apps/ai/deterministic_router.py
# ==============================================================================
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.ai.deterministic_router import (
    RouteCategory,
    RouteResult,
    classify_and_route,
    get_scoped_builders,
    is_qualified_status_query,
    _build_qualified_status_response,
    _extract_exclusion_term,
    should_skip_semantic_memory,
    _match_routine_time_query,
    _match_weight_query,
    _match_workout_query,
    _match_sleep_query,
    _match_glucose_query,
    _match_medication_query,
    _match_steps_query,
    _match_blood_pressure_query,
    _match_heart_rate_query,
)


# ==============================================================================
# Route Result Tests
# ==============================================================================

class RouteResultTests(TestCase):
    """Tests for the RouteResult data object."""

    def test_default_is_fallthrough(self):
        result = RouteResult()
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)
        self.assertIsNone(result.response)
        self.assertFalse(result.is_terminal)

    def test_deterministic_data_result(self):
        result = RouteResult(
            category=RouteCategory.DETERMINISTIC_DATA,
            response="Your weight is 302.9 lbs.",
            route_name='weight_query',
            domain='health',
            is_terminal=True,
        )
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.domain, 'health')

    def test_checkin_prefilter_is_not_terminal(self):
        result = RouteResult(
            category=RouteCategory.CHECKIN_PREFILTER,
            is_terminal=False,
        )
        self.assertFalse(result.is_terminal)
        self.assertIsNone(result.response)


# ==============================================================================
# Feature Flag Tests
# ==============================================================================

class FeatureFlagTests(TestCase):
    """Tests for feature flag behavior."""

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=False)
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_router_disabled_returns_fallthrough(self, mock_gms):
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)
        self.assertEqual(result.route_name, 'router_disabled')

    @override_settings(WLJ_DETERMINISTIC_DATA_ROUTES_ENABLED=False)
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_data_routes_disabled_skips_data_routes(self, mock_gms):
        """Data routes disabled → weight query falls through (health summary doesn't match 'what's my weight')."""
        mock_gms.return_value = {'weight_current': 300}
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        # Should fall through since data routes are disabled and this
        # doesn't match health summary or check-in patterns
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)


# ==============================================================================
# Weight Query Route Tests
# ==============================================================================

class WeightQueryMatcherTests(TestCase):
    """Tests for weight query lexical matching."""

    def test_whats_my_weight(self):
        self.assertTrue(_match_weight_query("what's my weight?"))

    def test_how_much_do_i_weigh(self):
        self.assertTrue(_match_weight_query("how much do i weigh?"))

    def test_current_weight(self):
        self.assertTrue(_match_weight_query("current weight"))

    def test_show_my_weight(self):
        self.assertTrue(_match_weight_query("show me my weight"))

    def test_excludes_log_weight(self):
        """Logging intent should NOT match."""
        self.assertFalse(_match_weight_query("log my weight at 300 lbs"))

    def test_excludes_set_weight(self):
        self.assertFalse(_match_weight_query("set my weight to 300"))

    def test_general_weight_discussion(self):
        """Generic weight mention without query intent → no match."""
        self.assertFalse(_match_weight_query("weight loss tips"))

    def test_no_match_unrelated(self):
        self.assertFalse(_match_weight_query("what should I eat today?"))


class WeightQueryHandlerTests(TestCase):
    """Tests for weight query deterministic handler."""

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_weight_with_trend(self, mock_gms):
        mock_gms.return_value = {
            'weight_current': 302.9,
            'weight_unit': 'lb',
            'weight_trend': 'decreasing',
        }
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('302.9 lbs', result.response)
        self.assertIn('trending down', result.response)
        self.assertTrue(result.is_terminal)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_weight_with_goal(self, mock_gms):
        mock_gms.return_value = {
            'weight_current': 302.9,
            'weight_unit': 'lb',
            'weight_trend': 'decreasing',
            'weight_goal': 250.0,
            'weight_goal_unit': 'lb',
            'weight_goal_remaining': 52.9,
            'weight_goal_on_track': True,
        }
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        self.assertIn('250 lbs', result.response)
        self.assertIn('52.9 lbs to go', result.response)
        self.assertIn('on track', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_no_weight_data_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        # No weight data → handler returns None → falls through
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)


# ==============================================================================
# Workout Query Route Tests
# ==============================================================================

class WorkoutQueryMatcherTests(TestCase):

    def test_how_many_workouts(self):
        self.assertTrue(_match_workout_query("how many workouts this week?"))

    def test_my_workouts(self):
        self.assertTrue(_match_workout_query("my workouts"))

    def test_exercise_this_week(self):
        self.assertTrue(_match_workout_query("exercise this week"))

    def test_excludes_log_workout(self):
        self.assertFalse(_match_workout_query("log a workout"))

    def test_excludes_start_workout(self):
        self.assertFalse(_match_workout_query("start a workout"))

    def test_no_match_unrelated(self):
        self.assertFalse(_match_workout_query("what time is it?"))


class WorkoutQueryHandlerTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_workout_count(self, mock_gms):
        mock_gms.return_value = {
            'workouts_7d': 5,
            'workout_minutes_7d': 300,
            'avg_workout_duration': 60,
        }
        user = MagicMock()
        result = classify_and_route("how many workouts this week?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('5 sessions', result.response)
        self.assertIn('5.0 hours', result.response)
        self.assertTrue(result.is_terminal)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_zero_workouts(self, mock_gms):
        mock_gms.return_value = {'workouts_7d': 0}
        user = MagicMock()
        result = classify_and_route("how many workouts this week?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('No workouts logged', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_single_workout_uses_singular(self, mock_gms):
        mock_gms.return_value = {'workouts_7d': 1}
        user = MagicMock()
        result = classify_and_route("how many workouts this week?", user)
        self.assertIn('1 session', result.response)
        self.assertNotIn('1 sessions', result.response)


# ==============================================================================
# Sleep Query Route Tests
# ==============================================================================

class SleepQueryMatcherTests(TestCase):

    def test_how_did_i_sleep(self):
        self.assertTrue(_match_sleep_query("how did i sleep?"))

    def test_hows_my_sleep(self):
        self.assertTrue(_match_sleep_query("how's my sleep?"))

    def test_sleep_this_week(self):
        self.assertTrue(_match_sleep_query("sleep this week"))

    def test_excludes_log_sleep(self):
        self.assertFalse(_match_sleep_query("log my sleep"))

    def test_no_match_unrelated(self):
        self.assertFalse(_match_sleep_query("i can't sleep, help me"))


class SleepQueryHandlerTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_sleep_average(self, mock_gms):
        mock_gms.return_value = {
            'sleep_avg_duration_7d': 420.0,  # 7 hours
            'sleep_trend': 'stable',
        }
        user = MagicMock()
        result = classify_and_route("how did i sleep?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('7.0 hours', result.response)
        self.assertIn('consistent', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_below_target(self, mock_gms):
        mock_gms.return_value = {
            'sleep_avg_duration_7d': 360.0,  # 6 hours
        }
        user = MagicMock()
        result = classify_and_route("how did i sleep?", user)
        self.assertIn('6.0 hours', result.response)
        self.assertIn('below the 7-hour target', result.response)


# ==============================================================================
# Glucose Query Route Tests
# ==============================================================================

class GlucoseQueryMatcherTests(TestCase):

    def test_whats_my_glucose(self):
        self.assertTrue(_match_glucose_query("what's my glucose?"))

    def test_blood_sugar(self):
        self.assertTrue(_match_glucose_query("how's my blood sugar?"))

    def test_excludes_log_glucose(self):
        self.assertFalse(_match_glucose_query("log my glucose at 120"))

    def test_no_match_unrelated(self):
        self.assertFalse(_match_glucose_query("what should I eat?"))


class GlucoseQueryHandlerTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_glucose_average(self, mock_gms):
        mock_gms.return_value = {'glucose_avg_7d': 123}
        user = MagicMock()
        result = classify_and_route("what's my glucose?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('123 mg/dL', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_normal_range(self, mock_gms):
        mock_gms.return_value = {'glucose_avg_7d': 95}
        user = MagicMock()
        result = classify_and_route("what's my glucose?", user)
        self.assertIn('normal range', result.response)


# ==============================================================================
# Medication Query Route Tests
# ==============================================================================

class MedicationQueryMatcherTests(TestCase):

    def test_did_i_take_my_meds(self):
        self.assertTrue(_match_medication_query("did i take my meds?"))

    def test_medication_status(self):
        self.assertTrue(_match_medication_query("medication status"))

    def test_med_check(self):
        self.assertTrue(_match_medication_query("med check"))

    def test_excludes_take_action(self):
        """'take my medication now' is an action, not a query."""
        self.assertFalse(_match_medication_query("take my medication now"))

    def test_excludes_log_meds(self):
        self.assertFalse(_match_medication_query("log my meds"))

    def test_no_match_unrelated(self):
        self.assertFalse(_match_medication_query("when is my next appointment?"))


class MedicationQueryHandlerTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_adherence(self, mock_gms):
        mock_gms.return_value = {
            'active_count': 3,
            'adherence_7d': 0.929,
            'today_taken': 2,
            'today_missed': 0,
            'today_pending': 1,
            'expected_today': 3,
        }
        user = MagicMock()
        result = classify_and_route("did i take my meds?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('93%', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_no_schedules(self, mock_gms):
        mock_gms.return_value = {
            'active_count': 0,
        }
        user = MagicMock()
        result = classify_and_route("did i take my meds?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('No active medication schedules', result.response)


# ==============================================================================
# Steps Query Route Tests
# ==============================================================================

class StepsQueryMatcherTests(TestCase):

    def test_how_many_steps(self):
        self.assertTrue(_match_steps_query("how many steps today?"))

    def test_my_steps(self):
        self.assertTrue(_match_steps_query("my steps"))

    def test_step_count(self):
        self.assertTrue(_match_steps_query("step count"))

    def test_excludes_log(self):
        self.assertFalse(_match_steps_query("log 10000 steps"))

    def test_no_match_unrelated(self):
        self.assertFalse(_match_steps_query("what's for dinner?"))


class StepsQueryHandlerTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_returns_step_average(self, mock_gms):
        mock_gms.return_value = {'steps_avg_7d': 8500}
        user = MagicMock()
        result = classify_and_route("how many steps today?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('8,500 steps', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_above_10k(self, mock_gms):
        mock_gms.return_value = {'steps_avg_7d': 12000}
        user = MagicMock()
        result = classify_and_route("how many steps today?", user)
        self.assertIn('excellent', result.response)


# ==============================================================================
# Blood Pressure & Heart Rate Tests
# ==============================================================================

class BloodPressureQueryTests(TestCase):

    def test_matcher_blood_pressure(self):
        self.assertTrue(_match_blood_pressure_query("blood pressure"))
        self.assertTrue(_match_blood_pressure_query("what's my bp?"))

    def test_matcher_excludes_log(self):
        self.assertFalse(_match_blood_pressure_query("log blood pressure 120/80"))

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_handler_returns_reading(self, mock_gms):
        mock_gms.return_value = {'bp_systolic': 128, 'bp_diastolic': 82}
        user = MagicMock()
        result = classify_and_route("blood pressure", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('128/82', result.response)


class HeartRateQueryTests(TestCase):

    def test_matcher_heart_rate(self):
        self.assertTrue(_match_heart_rate_query("what's my heart rate?"))
        self.assertTrue(_match_heart_rate_query("resting heart rate"))

    def test_matcher_excludes_log(self):
        self.assertFalse(_match_heart_rate_query("log heart rate 72"))

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_handler_returns_hr(self, mock_gms):
        mock_gms.return_value = {'heart_rate_avg_7d': 72}
        user = MagicMock()
        result = classify_and_route("what's my heart rate?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertIn('72 bpm', result.response)


# ==============================================================================
# Health Summary Fast Path Tests (preserved existing behavior)
# ==============================================================================

class HealthSummaryRouteTests(TestCase):
    """Verify the existing health summary fast path still works through router."""

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_health_summary_still_works(self, mock_gms):
        mock_gms.side_effect = lambda user, module: {
            'health': {
                'weight_current': 302.9,
                'weight_unit': 'lb',
                'weight_trend': 'decreasing',
            },
            'fitness': {'workouts_7d': 16},
        }.get(module, {})

        user = MagicMock()
        result = classify_and_route(
            "I have been working hard on my health, how have I been doing overall?",
            user,
        )
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_HEALTH_SUMMARY)
        self.assertTrue(result.is_terminal)
        self.assertIn('302.9 lbs', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_hows_my_health(self, mock_gms):
        mock_gms.side_effect = lambda user, module: {
            'health': {'weight_current': 300, 'weight_unit': 'lb'},
            'fitness': {},
        }.get(module, {})

        user = MagicMock()
        result = classify_and_route("how's my health?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_HEALTH_SUMMARY)


# ==============================================================================
# Strict Health Status Route Tests
# ==============================================================================

class StrictHealthStatusRouteTests(TestCase):

    def test_matches_strict_health_with_brevity(self):
        user = MagicMock()
        result = classify_and_route(
            "fat loss phase and plateau risk, keep it short",
            user,
            cos_context_cache={'health_intelligence': {
                'body_comp': {
                    'fat_loss_phase': 'STABLE_FAT_LOSS',
                    'plateau_risk_label': 'LOW',
                    'muscle_preservation_status': 'HIGH_QUALITY',
                },
                'last_computed': '2026-03-11T08:00:00',
            }},
        )
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_STRICT_HEALTH)
        self.assertIn('STABLE_FAT_LOSS', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_no_match_without_brevity(self, mock_gms):
        """Must have BOTH health intel keywords AND brevity keywords."""
        user = MagicMock()
        result = classify_and_route("fat loss phase and plateau risk", user)
        # No brevity keyword → falls through (not strict health, not data route)
        self.assertNotEqual(result.category, RouteCategory.DETERMINISTIC_STRICT_HEALTH)


# ==============================================================================
# Check-in Prefilter Route Tests
# ==============================================================================

class CheckinPrefilterRouteTests(TestCase):

    @patch('apps.ai.cos_fact_statements.build_locked_facts')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_checkin_query_detected(self, mock_gms, mock_facts):
        mock_gms.return_value = {}
        mock_facts.return_value = {
            'faith_summary': '', 'routine_summary': '', 'task_summary': '',
            'workout_summary': '', 'journal_summary': '', 'overall_summary': '',
            'next_action': 'Start with Workout.',
            '_raw': {
                'prayer_done': False, 'prayer_expected': False,
                'bible_done': False, 'bible_expected': False,
                'workout_done': False, 'workout_expected': False,
                'journal_done': False, 'journal_expected': False,
                'routine_done': 0, 'routine_total': 0, 'tasks_done': 0,
            },
        }
        user = MagicMock()
        user.id = 1
        result = classify_and_route("what's left for me today?", user)
        # Now terminal — deterministic renderer handles it
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)
        self.assertIsNotNone(result.response)

    @patch('apps.ai.cos_fact_statements.build_locked_facts')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_status_update_detected(self, mock_gms, mock_facts):
        mock_gms.return_value = {}
        mock_facts.return_value = {
            'faith_summary': '', 'routine_summary': '', 'task_summary': '',
            'workout_summary': '', 'journal_summary': '', 'overall_summary': '',
            'next_action': 'Start with Workout.',
            '_raw': {
                'prayer_done': False, 'prayer_expected': False,
                'bible_done': False, 'bible_expected': False,
                'workout_done': False, 'workout_expected': False,
                'journal_done': False, 'journal_expected': False,
                'routine_done': 0, 'routine_total': 0, 'tasks_done': 0,
            },
        }
        user = MagicMock()
        user.id = 1
        result = classify_and_route("give me a status update", user)
        # Now terminal — deterministic renderer handles it
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)

    @patch('apps.ai.cos_fact_statements.build_locked_facts')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_briefing_detected(self, mock_gms, mock_facts):
        mock_gms.return_value = {}
        mock_facts.return_value = {
            'faith_summary': '', 'routine_summary': '', 'task_summary': '',
            'workout_summary': '', 'journal_summary': '', 'overall_summary': '',
            'next_action': 'Start with Workout.',
            '_raw': {
                'prayer_done': False, 'prayer_expected': False,
                'bible_done': False, 'bible_expected': False,
                'workout_done': False, 'workout_expected': False,
                'journal_done': False, 'journal_expected': False,
                'routine_done': 0, 'routine_total': 0, 'tasks_done': 0,
            },
        }
        user = MagicMock()
        user.id = 1
        result = classify_and_route("daily briefing", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)


# ==============================================================================
# Fallthrough / No Match Tests
# ==============================================================================

class FallthroughTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_general_conversation_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("how are you today?", user)
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_coaching_question_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route(
            "why is my weight stalling? can you analyze my patterns?",
            user,
        )
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_reflective_question_falls_through(self, mock_gms):
        """Reflective questions should NOT be caught by deterministic routes."""
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("am I making progress?", user)
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_emotional_question_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route(
            "I'm feeling discouraged about my health journey",
            user,
        )
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)

    def test_empty_message_falls_through(self):
        user = MagicMock()
        result = classify_and_route("", user)
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)

    def test_none_message_falls_through(self):
        user = MagicMock()
        result = classify_and_route(None, user)
        self.assertEqual(result.category, RouteCategory.FALLTHROUGH)


# ==============================================================================
# Ambiguous Query Safety Tests (Phase 3 — CRITICAL)
# ==============================================================================

class AmbiguousQuerySafetyTests(TestCase):
    """
    Ensure reflective/interpretive questions are NOT captured by data routes.
    These should fall through to the LLM for proper coaching responses.
    """

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_how_have_i_been_doing_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("how have I been doing?", user)
        # This is reflective — should not be captured by weight/workout/etc
        self.assertNotEqual(result.category, RouteCategory.DETERMINISTIC_DATA)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_what_do_you_think_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("what do you think about my progress?", user)
        self.assertNotEqual(result.category, RouteCategory.DETERMINISTIC_DATA)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_analyze_my_patterns_falls_through(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("analyze my workout patterns", user)
        # "analyze" is coaching, not data retrieval
        self.assertNotEqual(result.category, RouteCategory.DETERMINISTIC_DATA)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_weight_loss_tips_not_captured(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("give me weight loss tips", user)
        self.assertNotEqual(result.category, RouteCategory.DETERMINISTIC_DATA)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_i_cant_sleep_not_captured(self, mock_gms):
        """'I can't sleep' is emotional/coaching, not a data query."""
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("i can't sleep lately, help me", user)
        self.assertNotEqual(result.category, RouteCategory.DETERMINISTIC_DATA)


# ==============================================================================
# Domain Inference Tests
# ==============================================================================

class DomainInferenceTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_health_domain_inferred(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("tell me about my weight trend", user)
        # Falls through but domain should be inferred
        self.assertEqual(result.domain, 'health')

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_faith_domain_inferred(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("where am I in my bible reading plan?", user)
        self.assertEqual(result.domain, 'faith')

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_ambiguous_domain_returns_none(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("how am I doing today?", user)
        # "today" doesn't clearly map to one domain
        self.assertIsNone(result.domain)


# ==============================================================================
# Domain Scoping Tests
# ==============================================================================

class DomainScopingTests(TestCase):

    @override_settings(WLJ_DOMAIN_SCOPED_CONTEXT_ENABLED=True)
    def test_health_domain_includes_related_builders(self):
        builders = get_scoped_builders('health')
        self.assertIn('health', builders)
        self.assertIn('meals', builders)
        self.assertIn('medical', builders)
        self.assertIn('blueprint', builders)  # Core builder

    @override_settings(WLJ_DOMAIN_SCOPED_CONTEXT_ENABLED=True)
    def test_none_domain_returns_none(self):
        """Ambiguous domain → full build."""
        builders = get_scoped_builders(None)
        self.assertIsNone(builders)

    @override_settings(WLJ_DOMAIN_SCOPED_CONTEXT_ENABLED=False)
    def test_disabled_returns_none(self):
        """Feature disabled → always full build."""
        builders = get_scoped_builders('health')
        self.assertIsNone(builders)


# ==============================================================================
# Semantic Memory Gating Tests
# ==============================================================================

class SemanticMemoryGatingTests(TestCase):

    @override_settings(WLJ_MEMORY_GATING_ENABLED=True)
    def test_skip_for_deterministic_data(self):
        result = RouteResult(category=RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(should_skip_semantic_memory(result))

    @override_settings(WLJ_MEMORY_GATING_ENABLED=True)
    def test_skip_for_health_summary(self):
        result = RouteResult(category=RouteCategory.DETERMINISTIC_HEALTH_SUMMARY)
        self.assertTrue(should_skip_semantic_memory(result))

    @override_settings(WLJ_MEMORY_GATING_ENABLED=True)
    def test_no_skip_for_checkin(self):
        result = RouteResult(category=RouteCategory.CHECKIN_PREFILTER)
        self.assertFalse(should_skip_semantic_memory(result))

    @override_settings(WLJ_MEMORY_GATING_ENABLED=True)
    def test_no_skip_for_fallthrough(self):
        result = RouteResult(category=RouteCategory.FALLTHROUGH)
        self.assertFalse(should_skip_semantic_memory(result))

    @override_settings(WLJ_MEMORY_GATING_ENABLED=False)
    def test_disabled_never_skips(self):
        result = RouteResult(category=RouteCategory.DETERMINISTIC_DATA)
        self.assertFalse(should_skip_semantic_memory(result))


# ==============================================================================
# Observability Tests
# ==============================================================================

class ObservabilityTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_route_result_has_timing(self, mock_gms):
        mock_gms.return_value = {'weight_current': 300, 'weight_unit': 'lb'}
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        self.assertGreater(result.elapsed_ms, 0)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_fallthrough_has_timing(self, mock_gms):
        mock_gms.return_value = {}
        user = MagicMock()
        result = classify_and_route("tell me a joke", user)
        self.assertGreater(result.elapsed_ms, 0)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_route_result_has_route_name(self, mock_gms):
        mock_gms.return_value = {'weight_current': 300, 'weight_unit': 'lb'}
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        self.assertEqual(result.route_name, 'weight_query')


# ==============================================================================
# Error Handling Tests
# ==============================================================================

class ErrorHandlingTests(TestCase):

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_handler_exception_falls_through(self, mock_gms):
        """If a handler throws, the router should fall through safely."""
        mock_gms.side_effect = Exception("DB connection lost")
        user = MagicMock()
        # Should not raise — should fall through gracefully
        result = classify_and_route("what's my weight?", user)
        # Either falls through to health summary (which also fails)
        # then to checkin prefilter (no match) → fallthrough
        self.assertIn(result.category, [
            RouteCategory.FALLTHROUGH,
            RouteCategory.CHECKIN_PREFILTER,
        ])


# ==============================================================================
# Insight Invitation Tests
# ==============================================================================

class InsightInvitationTests(TestCase):
    """Test that deterministic data responses include insight invitations where appropriate."""

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_weight_trend_includes_insight_invitation(self, mock_gms):
        mock_gms.return_value = {
            'weight_current': 302.9,
            'weight_unit': 'lb',
            'weight_trend': 'decreasing',
        }
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        self.assertIn('driving the trend', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_active_workouts_include_insight_invitation(self, mock_gms):
        mock_gms.return_value = {
            'workouts_7d': 5,
            'workout_minutes_7d': 300,
        }
        user = MagicMock()
        result = classify_and_route("how many workouts this week?", user)
        self.assertIn('training patterns', result.response)

    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_stable_weight_no_invitation(self, mock_gms):
        """Stable weight without trend → no insight invitation forced."""
        mock_gms.return_value = {
            'weight_current': 302.9,
            'weight_unit': 'lb',
            'weight_trend': 'stable',
        }
        user = MagicMock()
        result = classify_and_route("what's my weight?", user)
        # Should have weight info but may or may not have invitation
        self.assertIn('302.9 lbs', result.response)


class RoutineTimeQueryMatcherTests(TestCase):
    """Test _match_routine_time_query pattern matching."""

    def test_when_is_my_workout(self):
        self.assertEqual(_match_routine_time_query("when is my workout?"), "workout")

    def test_when_is_my_workout_no_question_mark(self):
        self.assertEqual(_match_routine_time_query("when is my workout"), "workout")

    def test_what_time_is_prayer(self):
        self.assertEqual(_match_routine_time_query("what time is prayer?"), "prayer")

    def test_what_time_is_my_shower(self):
        self.assertEqual(_match_routine_time_query("what time is my shower?"), "shower")

    def test_when_is_bible_reading_scheduled(self):
        self.assertEqual(
            _match_routine_time_query("when is bible reading scheduled"),
            "bible reading",
        )

    def test_when_is_workout_today(self):
        self.assertEqual(
            _match_routine_time_query("when is workout today"),
            "workout",
        )

    def test_no_match_general_question(self):
        self.assertIsNone(_match_routine_time_query("tell me about workouts"))

    def test_no_match_how_many(self):
        self.assertIsNone(_match_routine_time_query("how many workouts this week?"))

    def test_no_match_check_in(self):
        self.assertIsNone(_match_routine_time_query("check in"))

    def test_no_match_move_command(self):
        self.assertIsNone(_match_routine_time_query("move workout to 6pm"))


# ==============================================================================
# Qualified Status Query Tests
# ==============================================================================

class QualifiedStatusQueryTests(TestCase):
    """Tests for is_qualified_status_query() — ensures filtered/follow-up
    status questions bypass terminal deterministic routes and reach the LLM."""

    # ── Exclusion prefix patterns ────────────────────────────────
    def test_other_than_x_anything_left(self):
        self.assertTrue(is_qualified_status_query(
            "other than nutrition, anything left?"
        ))

    def test_besides_x_whats_remaining(self):
        self.assertTrue(is_qualified_status_query(
            "besides meds, what's remaining?"
        ))

    def test_except_for_x_what_is_left(self):
        self.assertTrue(is_qualified_status_query(
            "except for reading, what is left today?"
        ))

    def test_apart_from_x_anything_else(self):
        self.assertTrue(is_qualified_status_query(
            "apart from my workout, anything else?"
        ))

    def test_aside_from_x(self):
        self.assertTrue(is_qualified_status_query(
            "aside from nutrition, what do i have left?"
        ))

    def test_excluding_x(self):
        self.assertTrue(is_qualified_status_query(
            "excluding meds, anything left to do?"
        ))

    def test_not_counting_x(self):
        self.assertTrue(is_qualified_status_query(
            "not counting prayer, is there anything left?"
        ))

    def test_outside_of_x(self):
        self.assertTrue(is_qualified_status_query(
            "outside of journal, what's left?"
        ))

    # ── Yes/no status closers ────────────────────────────────────
    def test_am_i_done(self):
        self.assertTrue(is_qualified_status_query("am i done?"))

    def test_am_i_done_for_today(self):
        self.assertTrue(is_qualified_status_query("am i done for today?"))

    def test_is_that_it(self):
        self.assertTrue(is_qualified_status_query("is that it?"))

    def test_is_that_everything(self):
        self.assertTrue(is_qualified_status_query("is that everything?"))

    def test_anything_else(self):
        self.assertTrue(is_qualified_status_query("anything else?"))

    def test_is_there_anything_else(self):
        self.assertTrue(is_qualified_status_query("is there anything else?"))

    def test_did_i_miss_anything(self):
        self.assertTrue(is_qualified_status_query("did i miss anything?"))

    def test_am_i_finished(self):
        self.assertTrue(is_qualified_status_query("am i finished?"))

    # ── Imperative exclusion verbs ────────────────────────────────
    def test_leave_out_x(self):
        self.assertTrue(is_qualified_status_query(
            "leave out nutrition — what's left?"
        ))

    def test_skip_x(self):
        self.assertTrue(is_qualified_status_query(
            "skip nutrition, what's left?"
        ))

    def test_forget_about_x(self):
        self.assertTrue(is_qualified_status_query(
            "forget about meds — anything remaining?"
        ))

    def test_ignore_x(self):
        self.assertTrue(is_qualified_status_query(
            "ignore journal, anything left?"
        ))

    def test_ignoring_x(self):
        self.assertTrue(is_qualified_status_query(
            "ignoring meds, what do i have left?"
        ))

    def test_without_counting_x(self):
        self.assertTrue(is_qualified_status_query(
            "without counting nutrition, anything left?"
        ))

    def test_minus_x(self):
        self.assertTrue(is_qualified_status_query(
            "minus nutrition, anything remaining?"
        ))

    def test_skipping_x(self):
        self.assertTrue(is_qualified_status_query(
            "skipping workout, what's left?"
        ))

    # ── MUST NOT match — unqualified queries stay on terminal routes ──
    def test_whats_left_today_not_qualified(self):
        self.assertFalse(is_qualified_status_query("what's left today?"))

    def test_anything_left_not_qualified(self):
        self.assertFalse(is_qualified_status_query("anything left?"))

    def test_check_in_not_qualified(self):
        self.assertFalse(is_qualified_status_query("check in"))

    def test_brief_me_not_qualified(self):
        self.assertFalse(is_qualified_status_query("brief me"))

    def test_whats_remaining_not_qualified(self):
        self.assertFalse(is_qualified_status_query("what's remaining?"))

    def test_status_not_qualified(self):
        self.assertFalse(is_qualified_status_query("status"))


class ExclusionExtractionTests(TestCase):
    """Tests for _extract_exclusion_term() — parses the excluded item."""

    def test_other_than_nutrition(self):
        self.assertEqual(
            _extract_exclusion_term("other than nutrition, anything left?"),
            "nutrition",
        )

    def test_besides_meds(self):
        self.assertEqual(
            _extract_exclusion_term("besides meds, what's remaining?"),
            "meds",
        )

    def test_skip_workout(self):
        self.assertEqual(
            _extract_exclusion_term("skip workout, am i done?"),
            "workout",
        )

    def test_forget_about_prayer(self):
        self.assertEqual(
            _extract_exclusion_term("forget about prayer, anything else?"),
            "prayer",
        )

    def test_excluding_bible_reading(self):
        self.assertEqual(
            _extract_exclusion_term("excluding bible reading, anything left?"),
            "bible reading",
        )

    def test_without_counting_nutrition(self):
        self.assertEqual(
            _extract_exclusion_term("without counting nutrition, anything left?"),
            "nutrition",
        )

    def test_no_exclusion_returns_none(self):
        self.assertIsNone(_extract_exclusion_term("am i done?"))

    def test_no_exclusion_anything_else(self):
        self.assertIsNone(_extract_exclusion_term("anything else?"))


class QualifiedStatusResponseTests(TestCase):
    """Tests for _build_qualified_status_response() — deterministic rendering."""

    _ONE_REMAINING = {
        'all_items': [], 'foundation': [], 'overdue': [],
        'coming_up': [], 'later': [
            {'sort_time': None, 'label': 'Nutrition (6:00 PM)',
             'item': {'name': 'Nutrition', 'completed': False}},
        ],
        'completed': [
            {'sort_time': None, 'label': 'Prayer',
             'item': {'name': 'Prayer', 'completed': True}},
        ],
        'next': 'Nutrition',
    }

    _ALL_DONE = {
        'all_items': [], 'foundation': [], 'overdue': [],
        'coming_up': [], 'later': [], 'completed': [
            {'sort_time': None, 'label': 'Prayer',
             'item': {'name': 'Prayer', 'completed': True}},
            {'sort_time': None, 'label': 'Nutrition',
             'item': {'name': 'Nutrition', 'completed': True}},
        ],
        'next': 'None',
    }

    _MULTIPLE_REMAINING = {
        'all_items': [], 'foundation': [], 'overdue': [],
        'coming_up': [
            {'sort_time': None, 'label': 'Workout',
             'item': {'name': 'Workout', 'completed': False}},
        ],
        'later': [
            {'sort_time': None, 'label': 'Nutrition (6:00 PM)',
             'item': {'name': 'Nutrition', 'completed': False}},
        ],
        'completed': [],
        'next': 'Workout',
    }

    @patch('apps.core.today.today_engine.get_today_context')
    def test_filtered_only_nutrition_left(self, mock_today):
        mock_today.return_value = self._ONE_REMAINING
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response(
            "other than nutrition, anything left?", user
        )
        self.assertEqual(result, "No \u2014 just nutrition left.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_boolean_one_left(self, mock_today):
        mock_today.return_value = self._ONE_REMAINING
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response("am i done?", user)
        self.assertEqual(result, "Not yet \u2014 1 item left: Nutrition.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_boolean_all_done(self, mock_today):
        mock_today.return_value = self._ALL_DONE
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response("am i done?", user)
        self.assertEqual(result, "Yes \u2014 you're done for today.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_delta_one_left(self, mock_today):
        mock_today.return_value = self._ONE_REMAINING
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response("anything else?", user)
        self.assertEqual(result, "Just Nutrition left.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_delta_all_done(self, mock_today):
        mock_today.return_value = self._ALL_DONE
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response("anything else?", user)
        self.assertEqual(result, "No \u2014 you're done for today.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_filtered_with_other_remaining(self, mock_today):
        """Excluding nutrition when workout is also remaining → reports workout."""
        mock_today.return_value = self._MULTIPLE_REMAINING
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response(
            "other than nutrition, anything left?", user
        )
        self.assertEqual(result, "Yes \u2014 Workout is also remaining.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_boolean_multiple_remaining(self, mock_today):
        mock_today.return_value = self._MULTIPLE_REMAINING
        user = MagicMock(); user.id = 1
        result = _build_qualified_status_response("am i done?", user)
        self.assertEqual(result, "Not yet \u2014 2 items left: Workout, Nutrition.")

    @patch('apps.core.today.today_engine.get_today_context')
    def test_no_praise_or_coaching(self, mock_today):
        """Response must never contain praise, coaching, or recap."""
        mock_today.return_value = self._ONE_REMAINING
        user = MagicMock(); user.id = 1
        for msg in ["am i done?", "anything else?",
                     "other than nutrition, anything left?"]:
            result = _build_qualified_status_response(msg, user)
            for bad in ['great job', 'well done', 'keep it up',
                        'you completed', 'nice work', 'good progress']:
                self.assertNotIn(bad, result.lower(),
                                 f"Response for {msg!r} contains {bad!r}")


class QualifiedStatusRouterIntegrationTests(TestCase):
    """Integration: qualified queries hit their own terminal deterministic route,
    NOT the full status/checkin renderers."""

    _MOCK_TODAY_CTX = {
        'all_items': [],
        'foundation': [],
        'overdue': [],
        'coming_up': [],
        'later': [
            {
                'sort_time': None,
                'label': 'Nutrition (6:00 PM)',
                'item': {'name': 'Nutrition', 'completed': False,
                         'priority': 'flexible', 'source': 'routine'},
            }
        ],
        'completed': [
            {'sort_time': None, 'label': 'Prayer',
             'item': {'name': 'Prayer', 'completed': True}},
        ],
        'next': 'Nutrition',
    }

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=True)
    @patch('apps.core.today.today_engine.get_today_context')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_other_than_x_is_terminal_deterministic(self, mock_gms, mock_today):
        """'other than nutrition, anything left?' → terminal deterministic."""
        mock_today.return_value = self._MOCK_TODAY_CTX
        user = MagicMock()
        user.id = 1
        result = classify_and_route(
            "other than nutrition, anything left?", user
        )
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'qualified_status')
        self.assertIn('nutrition', result.response.lower())

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=True)
    @patch('apps.core.today.today_engine.get_today_context')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_am_i_done_is_terminal_deterministic(self, mock_gms, mock_today):
        """'am I done?' → terminal deterministic with count."""
        mock_today.return_value = self._MOCK_TODAY_CTX
        user = MagicMock()
        user.id = 1
        result = classify_and_route("am I done?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'qualified_status')
        self.assertIn('Nutrition', result.response)

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=True)
    @patch('apps.core.today.today_engine.get_today_context')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_besides_x_is_terminal_deterministic(self, mock_gms, mock_today):
        """'besides reading, what's left?' → terminal deterministic."""
        mock_today.return_value = self._MOCK_TODAY_CTX
        user = MagicMock()
        user.id = 1
        result = classify_and_route(
            "besides reading, what's left?", user
        )
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'qualified_status')

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=True)
    @patch('apps.ai.beth_status_renderer.build_status_response',
           return_value="Remaining:\n\u2022 Nutrition")
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_unqualified_whats_left_still_terminal(self, mock_gms, mock_build):
        """'what's left today?' must STILL hit the status route (not qualified)."""
        user = MagicMock()
        user.id = 1
        result = classify_and_route("what's left today?", user)
        self.assertEqual(result.category, RouteCategory.DETERMINISTIC_DATA)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, 'status_query')

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=True)
    @patch('apps.core.today.today_engine.get_today_context')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_response_content_is_concise(self, mock_gms, mock_today):
        """Qualified status responses must be 1-2 sentences, no lists."""
        mock_today.return_value = self._MOCK_TODAY_CTX
        user = MagicMock()
        user.id = 1
        for msg in [
            "other than nutrition, anything left?",
            "am I done?",
            "anything else?",
        ]:
            result = classify_and_route(msg, user)
            self.assertIsNotNone(result.response, f"No response for: {msg}")
            # Must not contain list markers, headers, or coaching
            for bad in ['\n\u2022', '\n-', '\n*', '##', 'great job',
                        'well done', 'keep it up', 'you completed']:
                self.assertNotIn(bad, result.response,
                                 f"Response for {msg!r} contains {bad!r}")

    @override_settings(WLJ_DETERMINISTIC_ROUTER_ENABLED=True)
    @patch('apps.core.today.today_engine.get_today_context')
    @patch('apps.core.ai_state.state_engine.get_module_state')
    def test_all_done_scenario(self, mock_gms, mock_today):
        """When everything is complete, boolean query returns 'done'."""
        empty_ctx = {
            'all_items': [], 'foundation': [], 'overdue': [],
            'coming_up': [], 'later': [], 'completed': [
                {'sort_time': None, 'label': 'Prayer',
                 'item': {'name': 'Prayer', 'completed': True}},
            ],
            'next': 'None',
        }
        mock_today.return_value = empty_ctx
        user = MagicMock()
        user.id = 1
        result = classify_and_route("am I done?", user)
        self.assertIn('done', result.response.lower())
