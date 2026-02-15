"""
Test suite for Human Temporal Intelligence Engine (HTIE).
"""

from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytz
from django.test import TestCase, override_settings

from apps.core.time.ambiguity_detector import AmbiguityResult, detect_ambiguity
from apps.core.time.interpreter import InterpretationResult, interpret_human_time
from apps.core.time.parser import ParsedTimeInput, parse_time_expression
from apps.core.time.resolver import ResolvedTime, resolve_time_expression
from apps.core.time.system_clock import get_current_time


# Fixed reference: Saturday Feb 14, 2026 10:00 UTC
REF_TIME = datetime(2026, 2, 14, 10, 0, 0, tzinfo=pytz.UTC)


# ─── System Clock Tests ───


class SystemClockTests(TestCase):
    @override_settings(TIME_ZONE="UTC")
    def test_returns_timezone_aware(self):
        now = get_current_time()
        self.assertIsNotNone(now.tzinfo)

    @override_settings(TIME_ZONE="UTC")
    def test_default_uses_settings_timezone(self):
        now = get_current_time()
        self.assertEqual(str(now.tzinfo), "UTC")

    def test_explicit_timezone(self):
        now = get_current_time("America/New_York")
        self.assertIn("America/New_York", str(now.tzinfo))

    def test_never_naive(self):
        for tz_str in ["UTC", "America/Chicago", "Europe/London", "Asia/Tokyo"]:
            now = get_current_time(tz_str)
            self.assertIsNotNone(now.tzinfo, f"Naive datetime for {tz_str}")


# ─── Parser Tests ───


class ParserTests(TestCase):
    def test_empty_input(self):
        result = parse_time_expression("")
        self.assertFalse(result.has_time)

    def test_none_input(self):
        result = parse_time_expression(None)
        self.assertFalse(result.has_time)

    def test_no_time_expression(self):
        result = parse_time_expression("update my weight to 250 lbs")
        self.assertFalse(result.has_time)

    def test_extract_days_ago(self):
        result = parse_time_expression("update my weight to 250 lbs 3 days ago")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "3 days ago")
        self.assertIn("250", result.remaining_text)

    def test_extract_next_friday_at_time(self):
        result = parse_time_expression("schedule appointment next Friday at 2pm")
        self.assertTrue(result.has_time)
        self.assertIn("next Friday", result.time_expression)
        self.assertIn("2pm", result.time_expression)

    def test_extract_tomorrow(self):
        result = parse_time_expression("remind me tomorrow")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "tomorrow")

    def test_extract_yesterday(self):
        result = parse_time_expression("I walked 5 miles yesterday")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "yesterday")

    def test_extract_in_90_minutes(self):
        result = parse_time_expression("check back in 90 minutes")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "in 90 minutes")

    def test_extract_last_week(self):
        result = parse_time_expression("I started my diet last week")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "last week")

    def test_extract_next_month(self):
        result = parse_time_expression("schedule for next month")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "next month")

    def test_extract_tomorrow_morning(self):
        result = parse_time_expression("remind me tomorrow morning")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "tomorrow morning")

    def test_extract_a_week_from_today(self):
        result = parse_time_expression("a week from today at 2pm")
        self.assertTrue(result.has_time)
        self.assertIn("week from today", result.time_expression)

    def test_extract_in_4_weeks(self):
        result = parse_time_expression("follow up in 4 weeks")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "in 4 weeks")

    def test_extract_recently(self):
        result = parse_time_expression("I updated my weight recently")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression, "recently")

    def test_extract_next_month_on_date(self):
        result = parse_time_expression(
            "schedule an appointment next month on the 15th at 10am"
        )
        self.assertTrue(result.has_time)
        self.assertIn("next month on the 15th", result.time_expression)

    def test_to_dict(self):
        result = parse_time_expression("update weight 3 days ago")
        d = result.to_dict()
        self.assertIn("original_input", d)
        self.assertIn("time_expression", d)
        self.assertIn("has_time", d)


# ─── Resolver Tests ───


class ResolverTests(TestCase):
    """All tests use REF_TIME = Saturday Feb 14, 2026 10:00 UTC."""

    def test_today(self):
        result = resolve_time_expression("today", REF_TIME)
        self.assertIsNotNone(result)
        self.assertEqual(result.datetime_aware.date(), REF_TIME.date())
        self.assertEqual(result.datetime_aware.hour, 0)

    def test_yesterday(self):
        result = resolve_time_expression("yesterday", REF_TIME)
        expected = (REF_TIME - timedelta(days=1)).date()
        self.assertEqual(result.datetime_aware.date(), expected)

    def test_tomorrow(self):
        result = resolve_time_expression("tomorrow", REF_TIME)
        expected = (REF_TIME + timedelta(days=1)).date()
        self.assertEqual(result.datetime_aware.date(), expected)

    def test_3_days_ago(self):
        result = resolve_time_expression("3 days ago", REF_TIME)
        self.assertIsNotNone(result)
        expected = datetime(2026, 2, 11, 10, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(result.datetime_aware, expected)

    def test_in_4_weeks(self):
        result = resolve_time_expression("in 4 weeks", REF_TIME)
        expected = datetime(2026, 3, 14, 10, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(result.datetime_aware, expected)

    def test_next_month(self):
        result = resolve_time_expression("next month", REF_TIME)
        self.assertEqual(result.datetime_aware.month, 3)
        self.assertEqual(result.datetime_aware.day, 1)
        self.assertEqual(result.datetime_aware.hour, 0)

    def test_last_month(self):
        result = resolve_time_expression("last month", REF_TIME)
        self.assertEqual(result.datetime_aware.month, 1)
        self.assertEqual(result.datetime_aware.day, 1)

    def test_tomorrow_at_2pm(self):
        result = resolve_time_expression("tomorrow at 2pm", REF_TIME)
        expected = datetime(2026, 2, 15, 14, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(result.datetime_aware, expected)

    def test_last_friday(self):
        # REF_TIME is Saturday Feb 14, so last Friday = Feb 13
        result = resolve_time_expression("last friday", REF_TIME)
        self.assertEqual(result.datetime_aware.date(), datetime(2026, 2, 13).date())

    def test_next_friday(self):
        # REF_TIME is Saturday Feb 14, so next Friday = Feb 20
        result = resolve_time_expression("next friday", REF_TIME)
        self.assertEqual(result.datetime_aware.date(), datetime(2026, 2, 20).date())

    def test_next_friday_at_2pm(self):
        result = resolve_time_expression("next friday at 2pm", REF_TIME)
        self.assertEqual(result.datetime_aware.date(), datetime(2026, 2, 20).date())
        self.assertEqual(result.datetime_aware.hour, 14)
        self.assertEqual(result.datetime_aware.minute, 0)

    def test_in_90_minutes(self):
        result = resolve_time_expression("in 90 minutes", REF_TIME)
        expected = REF_TIME + timedelta(minutes=90)
        self.assertEqual(result.datetime_aware, expected)

    def test_a_week_from_today(self):
        result = resolve_time_expression("a week from today", REF_TIME)
        expected = REF_TIME + timedelta(weeks=1)
        self.assertEqual(result.datetime_aware.date(), expected.date())

    def test_a_week_from_today_at_2pm(self):
        result = resolve_time_expression("a week from today at 2pm", REF_TIME)
        expected_date = (REF_TIME + timedelta(weeks=1)).date()
        self.assertEqual(result.datetime_aware.date(), expected_date)
        self.assertEqual(result.datetime_aware.hour, 14)

    def test_tomorrow_morning(self):
        result = resolve_time_expression("tomorrow morning", REF_TIME)
        expected = datetime(2026, 2, 15, 9, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(result.datetime_aware, expected)

    def test_yesterday_afternoon(self):
        result = resolve_time_expression("yesterday afternoon", REF_TIME)
        expected = datetime(2026, 2, 13, 14, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(result.datetime_aware, expected)

    def test_tonight(self):
        result = resolve_time_expression("tonight", REF_TIME)
        self.assertEqual(result.datetime_aware.date(), REF_TIME.date())
        self.assertEqual(result.datetime_aware.hour, 21)

    def test_last_week(self):
        result = resolve_time_expression("last week", REF_TIME)
        # Last Monday = Feb 2 (REF_TIME is Saturday Feb 14)
        self.assertEqual(result.datetime_aware.weekday(), 0)  # Monday
        self.assertTrue(result.datetime_aware < REF_TIME)

    def test_next_week(self):
        result = resolve_time_expression("next week", REF_TIME)
        # Next Monday from Saturday Feb 14 = Feb 16
        self.assertEqual(result.datetime_aware.weekday(), 0)  # Monday
        self.assertEqual(result.datetime_aware.date(), datetime(2026, 2, 16).date())

    def test_next_month_on_the_15th_at_10am(self):
        result = resolve_time_expression("next month on the 15th at 10am", REF_TIME)
        expected = datetime(2026, 3, 15, 10, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(result.datetime_aware, expected)

    def test_last_year(self):
        result = resolve_time_expression("last year", REF_TIME)
        self.assertEqual(result.datetime_aware.year, 2025)
        self.assertEqual(result.datetime_aware.month, 1)
        self.assertEqual(result.datetime_aware.day, 1)

    def test_next_year(self):
        result = resolve_time_expression("next year", REF_TIME)
        self.assertEqual(result.datetime_aware.year, 2027)

    def test_a_day_ago(self):
        result = resolve_time_expression("a day ago", REF_TIME)
        expected = REF_TIME - timedelta(days=1)
        self.assertEqual(result.datetime_aware, expected)

    def test_in_6_months(self):
        result = resolve_time_expression("in 6 months", REF_TIME)
        self.assertEqual(result.datetime_aware.month, 8)
        self.assertEqual(result.datetime_aware.year, 2026)

    def test_unresolvable_returns_none(self):
        result = resolve_time_expression("purple monkey dishwasher", REF_TIME)
        self.assertIsNone(result)

    def test_empty_returns_none(self):
        result = resolve_time_expression("", REF_TIME)
        self.assertIsNone(result)

    def test_none_returns_none(self):
        result = resolve_time_expression(None, REF_TIME)
        self.assertIsNone(result)

    def test_timezone_preserved(self):
        eastern = pytz.timezone("America/New_York")
        ref_eastern = datetime(2026, 2, 14, 10, 0, 0, tzinfo=eastern)
        result = resolve_time_expression("tomorrow", ref_eastern)
        self.assertEqual(result.datetime_aware.tzinfo, eastern)

    def test_to_dict(self):
        result = resolve_time_expression("3 days ago", REF_TIME)
        d = result.to_dict()
        self.assertIn("resolved_datetime", d)
        self.assertIn("confidence", d)
        self.assertEqual(d["confidence"], "high")

    def test_this_morning(self):
        result = resolve_time_expression("this morning", REF_TIME)
        self.assertEqual(result.datetime_aware.date(), REF_TIME.date())
        self.assertEqual(result.datetime_aware.hour, 9)

    def test_last_night(self):
        result = resolve_time_expression("last night", REF_TIME)
        expected_date = (REF_TIME - timedelta(days=1)).date()
        self.assertEqual(result.datetime_aware.date(), expected_date)
        self.assertEqual(result.datetime_aware.hour, 21)


# ─── Ambiguity Detector Tests ───


class AmbiguityDetectorTests(TestCase):
    def _make_parsed(self, time_expr):
        """Helper to create a ParsedTimeInput with a time expression."""
        return ParsedTimeInput(
            original_input=f"test {time_expr}",
            time_expression=time_expr,
            remaining_text="test",
        )

    def test_recently_is_ambiguous(self):
        parsed = self._make_parsed("recently")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertTrue(result.is_ambiguous)
        self.assertIsNotNone(result.clarification_question)

    def test_a_while_ago_is_ambiguous(self):
        parsed = self._make_parsed("a while ago")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertTrue(result.is_ambiguous)

    def test_the_other_day_is_ambiguous(self):
        parsed = self._make_parsed("the other day")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertTrue(result.is_ambiguous)

    def test_sometime_last_week_is_ambiguous(self):
        parsed = self._make_parsed("sometime last week")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertTrue(result.is_ambiguous)

    def test_3_days_ago_is_not_ambiguous(self):
        parsed = self._make_parsed("3 days ago")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertFalse(result.is_ambiguous)

    def test_tomorrow_at_2pm_is_not_ambiguous(self):
        parsed = self._make_parsed("tomorrow at 2pm")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertFalse(result.is_ambiguous)

    def test_next_day_same_as_today_is_ambiguous(self):
        # REF_TIME is Saturday. "next saturday" should be ambiguous.
        parsed = self._make_parsed("next saturday")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertTrue(result.is_ambiguous)
        self.assertEqual(result.reason, "same_day_ambiguity")
        self.assertEqual(len(result.candidates), 2)

    def test_next_day_different_from_today_is_not_ambiguous(self):
        # REF_TIME is Saturday. "next monday" is unambiguous.
        parsed = self._make_parsed("next monday")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertFalse(result.is_ambiguous)

    def test_no_time_expression_is_not_ambiguous(self):
        parsed = ParsedTimeInput("hello", None, "hello")
        result = detect_ambiguity(parsed, REF_TIME)
        self.assertFalse(result.is_ambiguous)

    def test_to_dict_ambiguous(self):
        parsed = self._make_parsed("recently")
        result = detect_ambiguity(parsed, REF_TIME)
        d = result.to_dict()
        self.assertTrue(d["is_ambiguous"])
        self.assertIn("clarification_question", d)

    def test_to_dict_not_ambiguous(self):
        parsed = self._make_parsed("3 days ago")
        result = detect_ambiguity(parsed, REF_TIME)
        d = result.to_dict()
        self.assertFalse(d["is_ambiguous"])


# ─── Interpreter (Orchestrator) Tests ───


class InterpreterTests(TestCase):
    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_full_pipeline_3_days_ago(self, mock_clock):
        result = interpret_human_time("update my weight to 250 lbs 3 days ago")
        self.assertTrue(result.success)
        self.assertEqual(
            result.resolved_time.datetime_aware.date(),
            datetime(2026, 2, 11).date(),
        )
        self.assertIn("250", result.remaining_text)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_full_pipeline_next_friday_at_2pm(self, mock_clock):
        result = interpret_human_time("schedule appointment next friday at 2pm")
        self.assertTrue(result.success)
        self.assertEqual(result.resolved_time.datetime_aware.hour, 14)
        self.assertEqual(
            result.resolved_time.datetime_aware.date(),
            datetime(2026, 2, 20).date(),
        )

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_ambiguous_returns_clarification(self, mock_clock):
        result = interpret_human_time("I updated my weight recently")
        self.assertFalse(result.success)
        self.assertTrue(result.is_ambiguous)
        self.assertIsNotNone(result.clarification_question)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_no_time_expression(self, mock_clock):
        result = interpret_human_time("update my weight to 250 lbs")
        self.assertFalse(result.success)
        self.assertIn("No time expression", result.error)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_empty_input(self, mock_clock):
        result = interpret_human_time("")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Empty input")

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_none_input(self, mock_clock):
        result = interpret_human_time(None)
        self.assertFalse(result.success)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_tomorrow_morning(self, mock_clock):
        result = interpret_human_time("remind me tomorrow morning")
        self.assertTrue(result.success)
        self.assertEqual(
            result.resolved_time.datetime_aware,
            datetime(2026, 2, 15, 9, 0, 0, tzinfo=pytz.UTC),
        )

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_in_90_minutes(self, mock_clock):
        result = interpret_human_time("check back in 90 minutes")
        self.assertTrue(result.success)
        expected = REF_TIME + timedelta(minutes=90)
        self.assertEqual(result.resolved_time.datetime_aware, expected)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_next_month_on_15th(self, mock_clock):
        result = interpret_human_time(
            "schedule an appointment next month on the 15th at 10am"
        )
        self.assertTrue(result.success)
        resolved = result.resolved_time.datetime_aware
        self.assertEqual(resolved.month, 3)
        self.assertEqual(resolved.day, 15)
        self.assertEqual(resolved.hour, 10)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_same_day_ambiguity(self, mock_clock):
        # REF_TIME is Saturday — "next saturday" is ambiguous
        result = interpret_human_time("meet next saturday")
        self.assertFalse(result.success)
        self.assertTrue(result.is_ambiguous)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_to_dict_success(self, mock_clock):
        result = interpret_human_time("update weight 3 days ago")
        d = result.to_dict()
        self.assertTrue(d["success"])
        self.assertIn("resolved_datetime", d)

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_to_dict_ambiguous(self, mock_clock):
        result = interpret_human_time("updated weight recently")
        d = result.to_dict()
        self.assertFalse(d["success"])
        self.assertTrue(d["is_ambiguous"])

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_user_timezone_passed_through(self, mock_clock):
        result = interpret_human_time("tomorrow", user_timezone="America/New_York")
        # Verify get_current_time was called with the timezone
        mock_clock.assert_called_with("America/New_York")

    @patch("apps.core.time.interpreter.get_current_time", return_value=REF_TIME)
    def test_a_week_from_today_at_2pm(self, mock_clock):
        result = interpret_human_time("a week from today at 2pm")
        self.assertTrue(result.success)
        resolved = result.resolved_time.datetime_aware
        self.assertEqual(resolved.date(), datetime(2026, 2, 21).date())
        self.assertEqual(resolved.hour, 14)
