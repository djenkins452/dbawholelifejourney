"""
Whole Life Journey - Human Translation Layer Tests

Project: Whole Life Journey
Path: apps/core/blueprint/tests_human_language.py
Purpose: Comprehensive tests for human_language.py translation functions

Description:
    Validates that all translate_* functions produce correct labels,
    descriptions, and human-readable output for all thresholds and
    edge cases.  Includes a critical compliance test ensuring no
    banned internal terms appear in any output.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.test import TestCase

from apps.core.blueprint.human_language import (
    _ordinal,
    get_status_line,
    translate_alignment,
    translate_capacity,
    translate_day_assessment,
    translate_drift_risk,
    translate_missed_commitment,
    translate_opportunity_window,
    translate_progress,
    translate_risk_warning,
    translate_weekly_pressure,
)

# -----------------------------------------------------------------
# Banned terms that must NEVER appear in user-facing output
# -----------------------------------------------------------------
BANNED_TERMS = [
    'Drift Monitor',
    'Governing',
    'T1',
    'Tier-1',
    'Tier 1',
    'protected commitment',
    'drift pressure',
    'drift risk',
    'density elevated',
    'governance',
]


class TranslateAlignmentTests(TestCase):
    """Tests for translate_alignment()."""

    def test_none_returns_calibrating(self):
        label, desc = translate_alignment(None)
        self.assertEqual(label, 'Calibrating')
        self.assertIn('baseline', desc)

    def test_locked_in_at_90(self):
        label, _ = translate_alignment(90)
        self.assertEqual(label, 'Locked in')

    def test_locked_in_at_100(self):
        label, desc = translate_alignment(100)
        self.assertEqual(label, 'Locked in')
        self.assertIn('exactly on plan', desc)

    def test_locked_in_at_95(self):
        label, _ = translate_alignment(95)
        self.assertEqual(label, 'Locked in')

    def test_steady_at_80(self):
        label, _ = translate_alignment(80)
        self.assertEqual(label, 'Steady')

    def test_steady_at_89(self):
        label, _ = translate_alignment(89)
        self.assertEqual(label, 'Steady')

    def test_drifting_slightly_at_65(self):
        label, _ = translate_alignment(65)
        self.assertEqual(label, 'Drifting slightly')

    def test_drifting_slightly_at_79(self):
        label, _ = translate_alignment(79)
        self.assertEqual(label, 'Drifting slightly')

    def test_under_pressure_at_50(self):
        label, _ = translate_alignment(50)
        self.assertEqual(label, 'Under pressure')

    def test_under_pressure_at_64(self):
        label, _ = translate_alignment(64)
        self.assertEqual(label, 'Under pressure')

    def test_off_course_at_49(self):
        label, _ = translate_alignment(49)
        self.assertEqual(label, 'Off course')

    def test_off_course_at_0(self):
        label, desc = translate_alignment(0)
        self.assertEqual(label, 'Off course')
        self.assertIn('Significant drift', desc)

    def test_negative_score_treated_as_off_course(self):
        label, _ = translate_alignment(-10)
        self.assertEqual(label, 'Off course')

    def test_float_score_is_truncated(self):
        # 89.9 should truncate to 89 -> 'Steady'
        label, _ = translate_alignment(89.9)
        self.assertEqual(label, 'Steady')


class TranslateDriftRiskTests(TestCase):
    """Tests for translate_drift_risk()."""

    def test_none_returns_unknown(self):
        label, desc = translate_drift_risk(None)
        self.assertEqual(label, 'Unknown')
        self.assertIn('Not enough data', desc)

    def test_clear_at_0(self):
        label, _ = translate_drift_risk(0)
        self.assertEqual(label, 'Clear')

    def test_clear_at_14(self):
        label, _ = translate_drift_risk(14)
        self.assertEqual(label, 'Clear')

    def test_low_risk_at_15(self):
        label, _ = translate_drift_risk(15)
        self.assertEqual(label, 'Low risk')

    def test_low_risk_at_24(self):
        label, _ = translate_drift_risk(24)
        self.assertEqual(label, 'Low risk')

    def test_moderate_at_25(self):
        label, _ = translate_drift_risk(25)
        self.assertEqual(label, 'Moderate')

    def test_moderate_at_39(self):
        label, _ = translate_drift_risk(39)
        self.assertEqual(label, 'Moderate')

    def test_elevated_at_40(self):
        label, _ = translate_drift_risk(40)
        self.assertEqual(label, 'Elevated')

    def test_elevated_at_59(self):
        label, desc = translate_drift_risk(59)
        self.assertEqual(label, 'Elevated')
        self.assertIn('margin', desc)

    def test_high_at_60(self):
        label, _ = translate_drift_risk(60)
        self.assertEqual(label, 'High')

    def test_high_at_79(self):
        label, _ = translate_drift_risk(79)
        self.assertEqual(label, 'High')

    def test_critical_at_80(self):
        label, _ = translate_drift_risk(80)
        self.assertEqual(label, 'Critical')

    def test_critical_at_100(self):
        label, desc = translate_drift_risk(100)
        self.assertEqual(label, 'Critical')
        self.assertIn('Overload', desc)

    def test_negative_drift_treated_as_clear(self):
        label, _ = translate_drift_risk(-5)
        self.assertEqual(label, 'Clear')


class TranslateCapacityTests(TestCase):
    """Tests for translate_capacity()."""

    def test_none_returns_no_plan(self):
        label, desc = translate_capacity(None)
        self.assertEqual(label, 'No plan')
        self.assertIn('No architecture', desc)

    def test_light_day_at_0(self):
        label, _ = translate_capacity(0)
        self.assertEqual(label, 'Light day')

    def test_light_day_at_19(self):
        label, _ = translate_capacity(19)
        self.assertEqual(label, 'Light day')

    def test_easy_pace_at_20(self):
        label, _ = translate_capacity(20)
        self.assertEqual(label, 'Easy pace')

    def test_easy_pace_at_39(self):
        label, _ = translate_capacity(39)
        self.assertEqual(label, 'Easy pace')

    def test_moderate_at_40(self):
        label, _ = translate_capacity(40)
        self.assertEqual(label, 'Moderate')

    def test_moderate_at_59(self):
        label, _ = translate_capacity(59)
        self.assertEqual(label, 'Moderate')

    def test_full_day_at_60(self):
        label, _ = translate_capacity(60)
        self.assertEqual(label, 'Full day')

    def test_full_day_at_79(self):
        label, _ = translate_capacity(79)
        self.assertEqual(label, 'Full day')

    def test_heavy_at_80(self):
        label, _ = translate_capacity(80)
        self.assertEqual(label, 'Heavy')

    def test_heavy_at_89(self):
        label, desc = translate_capacity(89)
        self.assertEqual(label, 'Heavy')
        self.assertIn('recovery', desc)

    def test_packed_at_90(self):
        label, _ = translate_capacity(90)
        self.assertEqual(label, 'Packed')

    def test_packed_at_100(self):
        label, desc = translate_capacity(100)
        self.assertEqual(label, 'Packed')
        self.assertIn('pressure', desc)

    def test_negative_capacity_treated_as_light(self):
        label, _ = translate_capacity(-1)
        self.assertEqual(label, 'Light day')


class TranslateProgressTests(TestCase):
    """Tests for translate_progress()."""

    def test_none_total_returns_no_blocks(self):
        label, desc = translate_progress(0, None)
        self.assertEqual(label, 'No blocks')
        self.assertIn('No scheduled', desc)

    def test_zero_total_returns_no_blocks(self):
        label, _ = translate_progress(0, 0)
        self.assertEqual(label, 'No blocks')

    def test_complete_at_100_pct(self):
        label, desc = translate_progress(5, 5)
        self.assertEqual(label, 'Complete')
        self.assertIn('done', desc)

    def test_almost_there_at_75_pct(self):
        label, desc = translate_progress(3, 4)
        self.assertEqual(label, 'Almost there')
        self.assertIn('1', desc)  # 1 remaining

    def test_almost_there_at_80_pct(self):
        label, _ = translate_progress(4, 5)
        self.assertEqual(label, 'Almost there')

    def test_half_done_at_50_pct(self):
        label, desc = translate_progress(5, 10)
        self.assertEqual(label, 'Half done')
        self.assertIn('5', desc)  # 5 remaining

    def test_half_done_at_60_pct(self):
        label, _ = translate_progress(6, 10)
        self.assertEqual(label, 'Half done')

    def test_getting_started(self):
        label, desc = translate_progress(1, 10)
        self.assertEqual(label, 'Getting started')
        self.assertIn('9', desc)  # 9 remaining
        self.assertIn('10', desc)  # out of 10

    def test_day_ahead_at_zero_completed(self):
        label, desc = translate_progress(0, 8)
        self.assertEqual(label, 'Day ahead')
        self.assertIn('8', desc)

    def test_none_completed_treated_as_zero(self):
        label, _ = translate_progress(None, 5)
        self.assertEqual(label, 'Day ahead')

    def test_single_item_complete(self):
        label, _ = translate_progress(1, 1)
        self.assertEqual(label, 'Complete')


class TranslateWeeklyPressureTests(TestCase):
    """Tests for translate_weekly_pressure()."""

    def test_none_returns_not_calculated(self):
        result = translate_weekly_pressure(None)
        self.assertEqual(result, 'Week not yet calculated.')

    def test_empty_dict_returns_not_calculated(self):
        result = translate_weekly_pressure({})
        self.assertEqual(result, 'Week not yet calculated.')

    def test_light_week(self):
        data = {'avg_load': 20, 'heavy_days': [], 'light_days': [], 'peak_day': '', 'peak_load': 0}
        result = translate_weekly_pressure(data)
        self.assertIn('Light week', result)

    def test_moderate_week(self):
        data = {'avg_load': 45, 'heavy_days': [], 'light_days': [], 'peak_day': '', 'peak_load': 0}
        result = translate_weekly_pressure(data)
        self.assertIn('Moderate week', result)

    def test_full_week(self):
        data = {'avg_load': 65, 'heavy_days': [], 'light_days': [], 'peak_day': '', 'peak_load': 0}
        result = translate_weekly_pressure(data)
        self.assertIn('Full week', result)

    def test_heavy_week(self):
        data = {'avg_load': 75, 'heavy_days': [], 'light_days': [], 'peak_day': '', 'peak_load': 0}
        result = translate_weekly_pressure(data)
        self.assertIn('Heavy week', result)

    def test_peak_day_included_when_load_high(self):
        data = {
            'avg_load': 50,
            'heavy_days': [],
            'light_days': [],
            'peak_day': 'Wednesday',
            'peak_load': 75,
        }
        result = translate_weekly_pressure(data)
        self.assertIn('Wednesday', result)
        self.assertIn('heavy', result)

    def test_peak_day_excluded_when_load_low(self):
        data = {
            'avg_load': 30,
            'heavy_days': [],
            'light_days': [],
            'peak_day': 'Monday',
            'peak_load': 50,
        }
        result = translate_weekly_pressure(data)
        self.assertNotIn('Monday', result)

    def test_peak_detail_included(self):
        data = {
            'avg_load': 50,
            'heavy_days': [],
            'light_days': [],
            'peak_day': 'Tuesday',
            'peak_load': 80,
            'peak_detail': '(morning packed)',
        }
        result = translate_weekly_pressure(data)
        self.assertIn('(morning packed)', result)

    def test_single_light_day(self):
        data = {
            'avg_load': 45,
            'heavy_days': [],
            'light_days': ['Saturday'],
            'peak_day': '',
            'peak_load': 0,
        }
        result = translate_weekly_pressure(data)
        self.assertIn('Saturday is open', result)

    def test_two_light_days(self):
        data = {
            'avg_load': 45,
            'heavy_days': [],
            'light_days': ['Saturday', 'Sunday'],
            'peak_day': '',
            'peak_load': 0,
        }
        result = translate_weekly_pressure(data)
        self.assertIn('Saturday and Sunday are open', result)

    def test_three_light_days(self):
        data = {
            'avg_load': 35,
            'heavy_days': [],
            'light_days': ['Friday', 'Saturday', 'Sunday'],
            'peak_day': '',
            'peak_load': 0,
        }
        result = translate_weekly_pressure(data)
        self.assertIn('Friday, Saturday and Sunday are open', result)

    def test_four_light_days_not_listed(self):
        """More than 3 light days should not be listed individually."""
        data = {
            'avg_load': 20,
            'heavy_days': [],
            'light_days': ['Wed', 'Thu', 'Fri', 'Sat'],
            'peak_day': '',
            'peak_load': 0,
        }
        result = translate_weekly_pressure(data)
        self.assertNotIn('are open', result)

    def test_overload_warning_with_many_heavy_days(self):
        data = {
            'avg_load': 70,
            'heavy_days': ['Monday', 'Tuesday', 'Wednesday'],
            'light_days': [],
            'peak_day': '',
            'peak_load': 0,
        }
        result = translate_weekly_pressure(data)
        self.assertIn('shifting one block', result)

    def test_no_overload_warning_with_two_heavy_days(self):
        data = {
            'avg_load': 60,
            'heavy_days': ['Monday', 'Tuesday'],
            'light_days': [],
            'peak_day': '',
            'peak_load': 0,
        }
        result = translate_weekly_pressure(data)
        self.assertNotIn('shifting', result)


class TranslateOpportunityWindowTests(TestCase):
    """Tests for translate_opportunity_window()."""

    def test_none_returns_empty(self):
        self.assertEqual(translate_opportunity_window(None), '')

    def test_empty_dict_returns_empty(self):
        self.assertEqual(translate_opportunity_window({}), '')

    def test_large_window_three_plus_hours(self):
        window = {
            'day_name': 'Saturday',
            'start_time': '9am',
            'end_time': '1pm',
            'duration_hours': 4,
        }
        result = translate_opportunity_window(window)
        self.assertIn('Saturday', result)
        self.assertIn('Good window', result)

    def test_medium_window_two_hours(self):
        window = {
            'day_name': 'Monday',
            'start_time': '2pm',
            'end_time': '4pm',
            'duration_hours': 2,
        }
        result = translate_opportunity_window(window)
        self.assertIn('2 free hours', result)

    def test_small_window_under_two_hours(self):
        window = {
            'day_name': 'Tuesday',
            'start_time': '11am',
            'end_time': '12pm',
            'duration_hours': 1,
        }
        result = translate_opportunity_window(window)
        self.assertIn('some space', result)

    def test_exactly_three_hours(self):
        window = {
            'day_name': 'Friday',
            'start_time': '1pm',
            'end_time': '4pm',
            'duration_hours': 3,
        }
        result = translate_opportunity_window(window)
        self.assertIn('Good window', result)

    def test_zero_duration(self):
        window = {
            'day_name': 'Wednesday',
            'start_time': '3pm',
            'end_time': '3pm',
            'duration_hours': 0,
        }
        result = translate_opportunity_window(window)
        self.assertIn('some space', result)


class TranslateDayAssessmentTests(TestCase):
    """Tests for translate_day_assessment()."""

    def test_light_day_no_extras(self):
        result = translate_day_assessment(10, 5, 0, 0, 0)
        self.assertIn('light day', result)

    def test_full_day_with_priorities(self):
        result = translate_day_assessment(65, 10, 3, 0, 5)
        self.assertIn('full day', result)
        self.assertIn('3 priorities locked in', result)

    def test_single_priority_uses_singular(self):
        result = translate_day_assessment(60, 10, 1, 0, 5)
        self.assertIn('1 priority locked in', result)
        self.assertNotIn('priorities', result)

    def test_drift_risk_shown_when_notable(self):
        result = translate_day_assessment(50, 45, 0, 0, 5)
        self.assertIn('Elevated risk', result)

    def test_drift_risk_hidden_when_low(self):
        result = translate_day_assessment(50, 10, 0, 0, 5)
        self.assertNotIn('risk', result.lower())

    def test_progress_shown_midday(self):
        result = translate_day_assessment(50, 10, 0, 3, 8)
        self.assertIn('Getting started', result)

    def test_progress_hidden_when_none_completed(self):
        result = translate_day_assessment(50, 10, 0, 0, 8)
        # Should not contain any progress label
        self.assertNotIn('Almost there', result)
        self.assertNotIn('Half done', result)
        self.assertNotIn('Getting started', result)

    def test_none_capacity_shows_no_plan(self):
        result = translate_day_assessment(None, None, None, None, None)
        self.assertIn('no plan', result)

    def test_packed_day_high_drift_all_done(self):
        result = translate_day_assessment(95, 85, 2, 10, 10)
        self.assertIn('packed', result)
        self.assertIn('Critical risk', result)
        self.assertIn('Complete', result)

    def test_zero_tier1_not_mentioned(self):
        result = translate_day_assessment(50, 10, 0, 0, 5)
        self.assertNotIn('locked in', result)

    def test_none_tier1_not_mentioned(self):
        result = translate_day_assessment(50, 10, None, 0, 5)
        self.assertNotIn('locked in', result)


class TranslateRiskWarningTests(TestCase):
    """Tests for translate_risk_warning()."""

    def test_none_returns_empty(self):
        self.assertEqual(translate_risk_warning(None), '')

    def test_empty_string_returns_empty(self):
        self.assertEqual(translate_risk_warning(''), '')

    def test_context_with_name_and_minutes_under_15(self):
        ctx = {
            'commitment_name': 'Morning Prayer',
            'time_remaining_minutes': 10,
            'recommended_action': 'Do it now',
        }
        result = translate_risk_warning('at_risk', context=ctx)
        self.assertIn('Morning Prayer', result)
        self.assertIn('10 minutes left', result)

    def test_context_with_name_and_minutes_over_15(self):
        ctx = {
            'commitment_name': 'Gym session',
            'time_remaining_minutes': 90,
            'recommended_action': '',
        }
        result = translate_risk_warning('at_risk', context=ctx)
        self.assertIn('Gym session', result)
        self.assertIn('1h 30m', result)

    def test_context_time_exact_hours(self):
        ctx = {
            'commitment_name': 'Reading',
            'time_remaining_minutes': 120,
        }
        result = translate_risk_warning('at_risk', context=ctx)
        self.assertIn('2h 0m', result)

    def test_context_window_passed(self):
        ctx = {
            'commitment_name': 'Meditation',
            'time_remaining_minutes': 0,
        }
        result = translate_risk_warning('at_risk', context=ctx)
        self.assertIn('Meditation', result)
        self.assertIn('passed', result)

    def test_context_negative_minutes_means_passed(self):
        ctx = {
            'commitment_name': 'Walk',
            'time_remaining_minutes': -30,
        }
        result = translate_risk_warning('missed', context=ctx)
        # -30 is <= 0, so window passed path
        self.assertIn('Walk', result)
        self.assertIn('passed', result)

    def test_context_name_and_action_no_minutes(self):
        ctx = {
            'commitment_name': 'Bible Study',
            'recommended_action': 'Reschedule to evening',
        }
        result = translate_risk_warning('suggestion', context=ctx)
        self.assertIn('Bible Study', result)
        self.assertIn('Reschedule to evening', result)

    def test_context_name_only(self):
        ctx = {'commitment_name': 'Journaling'}
        result = translate_risk_warning('needs_attention', context=ctx)
        self.assertIn('Journaling', result)
        self.assertIn('needs attention', result)

    def test_fallback_density_elevated(self):
        result = translate_risk_warning('Schedule density elevated for tomorrow')
        self.assertIn('dense', result)
        self.assertNotIn('density elevated', result.lower())

    def test_fallback_tier1(self):
        result = translate_risk_warning('Tier 1 commitment at risk')
        self.assertIn('top priorities', result)

    def test_fallback_tier_1_hyphenated(self):
        result = translate_risk_warning('Tier-1 block missed')
        self.assertIn('top priorities', result)

    def test_fallback_protected(self):
        result = translate_risk_warning('Protected commitment at risk')
        self.assertIn('top priorities', result)

    def test_fallback_sleep(self):
        result = translate_risk_warning('sleep not scheduled')
        self.assertIn('Sleep', result)

    def test_fallback_overload(self):
        result = translate_risk_warning('overload detected')
        self.assertIn('more load than typical', result)

    def test_passthrough_strips_tier1(self):
        result = translate_risk_warning('Your Tier-1 task is pending and Tier 1 check needed')
        self.assertNotIn('Tier-1', result)
        self.assertNotIn('Tier 1', result)
        self.assertIn('priorities', result)

    def test_context_with_15_minutes_exactly(self):
        """15 minutes should hit the <= 15 branch."""
        ctx = {
            'commitment_name': 'Stretch',
            'time_remaining_minutes': 15,
        }
        result = translate_risk_warning('at_risk', context=ctx)
        self.assertIn('15 minutes left', result)


class TranslateMissedCommitmentTests(TestCase):
    """Tests for translate_missed_commitment()."""

    def test_empty_name_returns_empty(self):
        self.assertEqual(translate_missed_commitment(''), '')

    def test_none_name_returns_empty(self):
        self.assertEqual(translate_missed_commitment(None), '')

    def test_time_remaining_under_15_minutes(self):
        result = translate_missed_commitment('Morning Prayer', time_remaining_minutes=10)
        self.assertIn('10 minutes left', result)
        self.assertIn('Morning Prayer', result)

    def test_time_remaining_under_60_minutes(self):
        result = translate_missed_commitment('Gym', time_remaining_minutes=45)
        self.assertIn('45 minutes', result)

    def test_time_remaining_over_60_minutes(self):
        result = translate_missed_commitment('Reading', time_remaining_minutes=90)
        self.assertIn('1h 30m', result)

    def test_time_remaining_exact_hours(self):
        result = translate_missed_commitment('Walk', time_remaining_minutes=120)
        self.assertIn('2 hours', result)
        self.assertNotIn('0m', result)  # No "2h 0m" - should say "2 hours"

    def test_time_remaining_zero_window_passed(self):
        result = translate_missed_commitment('Meditation', time_remaining_minutes=0)
        self.assertIn('window has passed', result)

    def test_time_remaining_negative_window_passed(self):
        result = translate_missed_commitment('Journaling', time_remaining_minutes=-15)
        self.assertIn('window has passed', result)

    def test_miss_count_three_standard(self):
        result = translate_missed_commitment('Gym', miss_count_week=3)
        self.assertIn('3rd miss', result)

    def test_miss_count_three_light(self):
        result = translate_missed_commitment('Gym', miss_count_week=3, accountability_style='light')
        self.assertIn('3 times this week', result)
        self.assertIn('worth thinking about', result)

    def test_miss_count_three_firm(self):
        result = translate_missed_commitment('Gym', miss_count_week=3, accountability_style='firm')
        self.assertIn('non-negotiable', result)
        self.assertIn('off track', result)

    def test_miss_count_two_standard(self):
        result = translate_missed_commitment('Prayer', miss_count_week=2)
        self.assertIn('Second miss', result)

    def test_miss_count_two_light_no_mention(self):
        result = translate_missed_commitment('Prayer', miss_count_week=2, accountability_style='light')
        self.assertNotIn('Second miss', result)

    def test_miss_count_one_no_pattern_mention(self):
        result = translate_missed_commitment('Walk', miss_count_week=1)
        self.assertNotIn('miss', result.lower())

    def test_combined_time_and_miss_count(self):
        result = translate_missed_commitment(
            'Morning Prayer',
            time_remaining_minutes=10,
            miss_count_week=4,
            accountability_style='standard',
        )
        self.assertIn('10 minutes left', result)
        self.assertIn('4th miss', result)

    def test_no_time_no_misses_returns_empty(self):
        """With no time info and zero misses, nothing to say."""
        result = translate_missed_commitment('Walk', time_remaining_minutes=None, miss_count_week=0)
        self.assertEqual(result, '')

    def test_exactly_15_minutes(self):
        result = translate_missed_commitment('Stretch', time_remaining_minutes=15)
        self.assertIn('15 minutes left', result)

    def test_exactly_60_minutes(self):
        # 60 is <= 60, so hits the "minutes to get X done" branch
        result = translate_missed_commitment('Reading', time_remaining_minutes=60)
        self.assertIn('60 minutes', result)


class OrdinalHelperTests(TestCase):
    """Tests for _ordinal() helper."""

    def test_first(self):
        self.assertEqual(_ordinal(1), '1st')

    def test_second(self):
        self.assertEqual(_ordinal(2), '2nd')

    def test_third(self):
        self.assertEqual(_ordinal(3), '3rd')

    def test_fourth(self):
        self.assertEqual(_ordinal(4), '4th')

    def test_eleventh(self):
        self.assertEqual(_ordinal(11), '11th')

    def test_twelfth(self):
        self.assertEqual(_ordinal(12), '12th')

    def test_thirteenth(self):
        self.assertEqual(_ordinal(13), '13th')

    def test_twenty_first(self):
        self.assertEqual(_ordinal(21), '21st')

    def test_twenty_second(self):
        self.assertEqual(_ordinal(22), '22nd')

    def test_hundred_eleventh(self):
        self.assertEqual(_ordinal(111), '111th')

    def test_hundred_twelfth(self):
        self.assertEqual(_ordinal(112), '112th')


class GetStatusLineTests(TestCase):
    """Tests for get_status_line()."""

    def test_none_drift_returns_clean(self):
        result = get_status_line(None)
        self.assertIn('Running clean', result)

    def test_low_drift_running_clean(self):
        result = get_status_line(10)
        self.assertIn('Running clean', result)

    def test_moderate_pressure(self):
        result = get_status_line(30)
        self.assertIn('Moderate pressure', result)

    def test_boundary_25_is_moderate(self):
        result = get_status_line(25)
        self.assertIn('Moderate pressure', result)

    def test_high_pressure(self):
        result = get_status_line(60)
        self.assertIn('Under pressure', result)

    def test_boundary_50_is_high(self):
        result = get_status_line(50)
        self.assertIn('Under pressure', result)

    def test_zero_drift_running_clean(self):
        result = get_status_line(0)
        self.assertIn('Running clean', result)


# ===================================================================
# CRITICAL: Banned Terms Compliance Test
# ===================================================================

class BannedTermsComplianceTests(TestCase):
    """
    CRITICAL TEST: No internal/banned terms may appear in ANY
    user-facing output from the human_language module.

    Calls every function with a wide variety of inputs and asserts
    that none of the banned terms appear in any output.
    """

    def _check_no_banned_terms(self, text, context_msg=''):
        """Assert that text contains none of the banned terms (case-insensitive)."""
        if not text:
            return
        text_lower = text.lower()
        for term in BANNED_TERMS:
            self.assertNotIn(
                term.lower(),
                text_lower,
                f"Banned term '{term}' found in output: '{text}' {context_msg}",
            )

    def _check_tuple(self, result, context_msg=''):
        """Check a (label, description) tuple for banned terms."""
        label, desc = result
        self._check_no_banned_terms(label, context_msg)
        self._check_no_banned_terms(desc, context_msg)

    def test_translate_alignment_no_banned_terms(self):
        test_scores = [None, -10, 0, 10, 25, 49, 50, 64, 65, 79, 80, 89, 90, 95, 100]
        for score in test_scores:
            self._check_tuple(
                translate_alignment(score),
                f"(translate_alignment({score}))",
            )

    def test_translate_drift_risk_no_banned_terms(self):
        test_pcts = [None, -5, 0, 14, 15, 24, 25, 39, 40, 59, 60, 79, 80, 100]
        for pct in test_pcts:
            self._check_tuple(
                translate_drift_risk(pct),
                f"(translate_drift_risk({pct}))",
            )

    def test_translate_capacity_no_banned_terms(self):
        test_pcts = [None, -1, 0, 19, 20, 39, 40, 59, 60, 79, 80, 89, 90, 100]
        for pct in test_pcts:
            self._check_tuple(
                translate_capacity(pct),
                f"(translate_capacity({pct}))",
            )

    def test_translate_progress_no_banned_terms(self):
        test_cases = [
            (0, None), (0, 0), (0, 5), (1, 10), (3, 8), (5, 10),
            (7, 10), (10, 10), (None, 5), (None, None),
        ]
        for completed, total in test_cases:
            self._check_tuple(
                translate_progress(completed, total),
                f"(translate_progress({completed}, {total}))",
            )

    def test_translate_weekly_pressure_no_banned_terms(self):
        test_cases = [
            None,
            {},
            {'avg_load': 20, 'heavy_days': [], 'light_days': [], 'peak_day': '', 'peak_load': 0},
            {'avg_load': 45, 'heavy_days': [], 'light_days': ['Sat'], 'peak_day': '', 'peak_load': 0},
            {'avg_load': 65, 'heavy_days': [], 'light_days': ['Sat', 'Sun'], 'peak_day': 'Mon', 'peak_load': 80},
            {'avg_load': 75, 'heavy_days': ['Mon', 'Tue', 'Wed'], 'light_days': [], 'peak_day': 'Mon', 'peak_load': 90},
            {'avg_load': 50, 'heavy_days': [], 'light_days': ['Fri', 'Sat', 'Sun'], 'peak_day': 'Tue', 'peak_load': 70, 'peak_detail': '(AM dense)'},
        ]
        for data in test_cases:
            result = translate_weekly_pressure(data)
            self._check_no_banned_terms(
                result,
                f"(translate_weekly_pressure({data}))",
            )

    def test_translate_opportunity_window_no_banned_terms(self):
        test_cases = [
            None,
            {},
            {'day_name': 'Mon', 'start_time': '9am', 'end_time': '12pm', 'duration_hours': 3},
            {'day_name': 'Tue', 'start_time': '2pm', 'end_time': '4pm', 'duration_hours': 2},
            {'day_name': 'Wed', 'start_time': '5pm', 'end_time': '6pm', 'duration_hours': 1},
        ]
        for window in test_cases:
            result = translate_opportunity_window(window)
            self._check_no_banned_terms(
                result,
                f"(translate_opportunity_window({window}))",
            )

    def test_translate_day_assessment_no_banned_terms(self):
        test_cases = [
            (10, 5, 0, 0, 0),
            (50, 30, 2, 3, 10),
            (80, 60, 5, 8, 10),
            (95, 85, 1, 10, 10),
            (None, None, None, None, None),
            (0, 0, 0, 0, 0),
            (100, 100, 10, 0, 10),
        ]
        for args in test_cases:
            result = translate_day_assessment(*args)
            self._check_no_banned_terms(
                result,
                f"(translate_day_assessment{args})",
            )

    def test_translate_risk_warning_no_banned_terms(self):
        # Without context
        raw_warnings = [
            '',
            None,
            'Schedule density elevated for tomorrow',
            'Tier 1 commitment at risk',
            'Tier-1 block missed',
            'Protected commitment at risk',
            'sleep not scheduled',
            'overload detected',
            'General unknown warning text',
            'Your Tier-1 and Tier 1 items both need review',
        ]
        for w in raw_warnings:
            result = translate_risk_warning(w)
            self._check_no_banned_terms(
                result,
                f"(translate_risk_warning('{w}'))",
            )

        # With context
        contexts = [
            {'commitment_name': 'Prayer', 'time_remaining_minutes': 10},
            {'commitment_name': 'Gym', 'time_remaining_minutes': 90},
            {'commitment_name': 'Reading', 'time_remaining_minutes': 0},
            {'commitment_name': 'Walk', 'time_remaining_minutes': -5},
            {'commitment_name': 'Study', 'recommended_action': 'Reschedule'},
            {'commitment_name': 'Rest'},
        ]
        for ctx in contexts:
            result = translate_risk_warning('warning', context=ctx)
            self._check_no_banned_terms(
                result,
                f"(translate_risk_warning('warning', context={ctx}))",
            )

    def test_translate_missed_commitment_no_banned_terms(self):
        test_cases = [
            ('', None, 0, 'standard'),
            (None, None, 0, 'standard'),
            ('Prayer', 10, 0, 'standard'),
            ('Gym', 45, 2, 'standard'),
            ('Reading', 90, 3, 'light'),
            ('Walk', 120, 3, 'firm'),
            ('Study', 0, 5, 'standard'),
            ('Rest', -10, 4, 'standard'),
            ('Journaling', None, 0, 'light'),
            ('Bible Study', 15, 3, 'standard'),
        ]
        for name, time_rem, miss_count, style in test_cases:
            result = translate_missed_commitment(
                name,
                time_remaining_minutes=time_rem,
                miss_count_week=miss_count,
                accountability_style=style,
            )
            self._check_no_banned_terms(
                result,
                f"(translate_missed_commitment('{name}', {time_rem}, {miss_count}, '{style}'))",
            )

    def test_get_status_line_no_banned_terms(self):
        test_pcts = [None, 0, 10, 24, 25, 30, 49, 50, 60, 80, 100]
        for pct in test_pcts:
            result = get_status_line(pct)
            self._check_no_banned_terms(
                result,
                f"(get_status_line({pct}))",
            )
