"""
Unit tests for the Date Parser utility.

Tests cover various date formats and edge cases to ensure accurate
natural language date extraction.
"""

import unittest
from datetime import datetime, timedelta

from assistant.date_parser import extract_date_from_message


class TestExtractDateFromMessageBasic(unittest.TestCase):
    """Basic tests for extract_date_from_message function."""

    def test_returns_none_for_empty_string(self):
        """Empty string should return None."""
        result = extract_date_from_message("")
        self.assertIsNone(result)

    def test_returns_none_for_none_input(self):
        """None input should return None."""
        result = extract_date_from_message(None)
        self.assertIsNone(result)

    def test_returns_none_for_non_string(self):
        """Non-string input should return None."""
        result = extract_date_from_message(123)
        self.assertIsNone(result)

    def test_returns_none_for_no_date(self):
        """Message without date reference should return None."""
        result = extract_date_from_message("Hello, how are you?")
        self.assertIsNone(result)

    def test_returns_datetime_object(self):
        """Result should be a datetime object when date is found."""
        ref_date = datetime(2024, 12, 15)
        result = extract_date_from_message("What happened today?", ref_date)
        self.assertIsInstance(result, datetime)


class TestRelativeDates(unittest.TestCase):
    """Tests for relative date extraction."""

    def setUp(self):
        """Set up reference date for tests."""
        # Wednesday, December 18, 2024
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)
        self.today = datetime(2024, 12, 18, 0, 0, 0)

    def test_today(self):
        """Should extract 'today' correctly."""
        result = extract_date_from_message("What did I eat today?", self.ref_date)
        self.assertEqual(result, self.today)

    def test_yesterday(self):
        """Should extract 'yesterday' correctly."""
        result = extract_date_from_message("How did I sleep yesterday?", self.ref_date)
        expected = datetime(2024, 12, 17, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_this_week(self):
        """Should extract 'this week' as Monday of current week."""
        result = extract_date_from_message("My weight this week", self.ref_date)
        # Monday of the week containing Dec 18, 2024 (Wednesday)
        expected = datetime(2024, 12, 16, 0, 0, 0)  # Monday Dec 16
        self.assertEqual(result, expected)

    def test_last_week(self):
        """Should extract 'last week' as Monday of previous week."""
        result = extract_date_from_message("My mood last week", self.ref_date)
        # Monday of the previous week
        expected = datetime(2024, 12, 9, 0, 0, 0)  # Monday Dec 9
        self.assertEqual(result, expected)

    def test_this_month(self):
        """Should extract 'this month' as 1st of current month."""
        result = extract_date_from_message("My journal this month", self.ref_date)
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_last_month(self):
        """Should extract 'last month' as 1st of previous month."""
        result = extract_date_from_message("My exercise last month", self.ref_date)
        expected = datetime(2024, 11, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_this_year(self):
        """Should extract 'this year' as January 1st of current year."""
        result = extract_date_from_message("My progress this year", self.ref_date)
        expected = datetime(2024, 1, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_last_year(self):
        """Should extract 'last year' as January 1st of previous year."""
        result = extract_date_from_message("Compare to last year", self.ref_date)
        expected = datetime(2023, 1, 1, 0, 0, 0)
        self.assertEqual(result, expected)


class TestPastNDays(unittest.TestCase):
    """Tests for 'past N days/weeks/months' patterns."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)
        self.today = datetime(2024, 12, 18, 0, 0, 0)

    def test_past_7_days(self):
        """Should extract 'past 7 days'."""
        result = extract_date_from_message("My weight past 7 days", self.ref_date)
        expected = self.today - timedelta(days=7)
        self.assertEqual(result, expected)

    def test_last_30_days(self):
        """Should extract 'last 30 days'."""
        result = extract_date_from_message("Show my mood last 30 days", self.ref_date)
        expected = self.today - timedelta(days=30)
        self.assertEqual(result, expected)

    def test_past_2_weeks(self):
        """Should extract 'past 2 weeks'."""
        result = extract_date_from_message("My sleep past 2 weeks", self.ref_date)
        expected = self.today - timedelta(weeks=2)
        self.assertEqual(result, expected)

    def test_last_3_months(self):
        """Should extract 'last 3 months'."""
        result = extract_date_from_message("My progress last 3 months", self.ref_date)
        expected = datetime(2024, 9, 18, 0, 0, 0)  # 3 months before Dec 18
        self.assertEqual(result, expected)


class TestSinceFromAfterPhrases(unittest.TestCase):
    """Tests for 'since X', 'from X', 'after X' phrase extraction."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)

    def test_since_month_day(self):
        """Should extract date from 'since December 1st'."""
        result = extract_date_from_message(
            "What was my weight since December 1st?", self.ref_date
        )
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_since_abbreviated_month(self):
        """Should extract date from 'since Dec 1'."""
        result = extract_date_from_message(
            "My mood since Dec 1", self.ref_date
        )
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_from_date(self):
        """Should extract date from 'from November 15th'."""
        result = extract_date_from_message(
            "Show entries from November 15th", self.ref_date
        )
        expected = datetime(2024, 11, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_after_date(self):
        """Should extract date from 'after October 1'."""
        result = extract_date_from_message(
            "My exercise after October 1", self.ref_date
        )
        expected = datetime(2024, 10, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_since_last_week(self):
        """Should handle 'since last week'."""
        result = extract_date_from_message(
            "What did I journal since last week?", self.ref_date
        )
        # Monday of previous week
        expected = datetime(2024, 12, 9, 0, 0, 0)
        self.assertEqual(result, expected)


class TestMonthDayFormats(unittest.TestCase):
    """Tests for various month/day format parsing."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)

    def test_full_month_day(self):
        """Should parse 'December 15'."""
        result = extract_date_from_message("My weight on December 15", self.ref_date)
        expected = datetime(2024, 12, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_month_day_ordinal(self):
        """Should parse 'December 1st'."""
        result = extract_date_from_message("Since December 1st", self.ref_date)
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_abbreviated_month(self):
        """Should parse 'Jan 5'."""
        result = extract_date_from_message("My mood on Jan 5", self.ref_date)
        # January 5 is in the future relative to Dec 18, so assume last year
        expected = datetime(2024, 1, 5, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_day_month_format(self):
        """Should parse '15th November'."""
        result = extract_date_from_message("Entry on 15th November", self.ref_date)
        expected = datetime(2024, 11, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_just_month(self):
        """Should parse just month name as 1st of that month."""
        result = extract_date_from_message("My weight in November", self.ref_date)
        expected = datetime(2024, 11, 1, 0, 0, 0)
        self.assertEqual(result, expected)


class TestNumericDateFormats(unittest.TestCase):
    """Tests for numeric date format parsing."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)

    def test_mm_dd_format(self):
        """Should parse '12/15'."""
        result = extract_date_from_message("My weight on 12/15", self.ref_date)
        expected = datetime(2024, 12, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_mm_dd_yyyy_format(self):
        """Should parse '12/15/2024'."""
        result = extract_date_from_message("My weight on 12/15/2024", self.ref_date)
        expected = datetime(2024, 12, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_mm_dd_yy_format(self):
        """Should parse '12/15/24' (2-digit year)."""
        result = extract_date_from_message("My weight on 12/15/24", self.ref_date)
        expected = datetime(2024, 12, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_iso_format(self):
        """Should parse '2024-12-15'."""
        result = extract_date_from_message("Entry on 2024-12-15", self.ref_date)
        expected = datetime(2024, 12, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_dash_separated(self):
        """Should parse '12-15' format."""
        result = extract_date_from_message("My mood on 12-15", self.ref_date)
        expected = datetime(2024, 12, 15, 0, 0, 0)
        self.assertEqual(result, expected)


class TestYearDefaulting(unittest.TestCase):
    """Tests for year defaulting when year is not specified."""

    def test_past_date_uses_current_year(self):
        """Date in the past (within current year) should use current year."""
        ref_date = datetime(2024, 12, 18)
        result = extract_date_from_message("Since November 1", ref_date)
        expected = datetime(2024, 11, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_future_date_uses_previous_year(self):
        """Date more than a week in the future should use previous year."""
        ref_date = datetime(2024, 3, 15)  # March 15
        result = extract_date_from_message("Since December 1", ref_date)
        # December 1 is in the future relative to March, so use 2023
        expected = datetime(2023, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_near_future_uses_current_year(self):
        """Date within a week in the future should use current year."""
        ref_date = datetime(2024, 12, 20)  # December 20
        result = extract_date_from_message("Until December 25", ref_date)
        # December 25 is only 5 days away, use current year
        expected = datetime(2024, 12, 25, 0, 0, 0)
        self.assertEqual(result, expected)


class TestCaseInsensitivity(unittest.TestCase):
    """Tests for case-insensitive matching."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)

    def test_uppercase_month(self):
        """Should handle uppercase month names."""
        result = extract_date_from_message("Since DECEMBER 1st", self.ref_date)
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_mixed_case(self):
        """Should handle mixed case."""
        result = extract_date_from_message("Since DeCeMbEr 1st", self.ref_date)
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_uppercase_today(self):
        """Should handle 'TODAY'."""
        result = extract_date_from_message("What happened TODAY?", self.ref_date)
        expected = datetime(2024, 12, 18, 0, 0, 0)
        self.assertEqual(result, expected)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)

    def test_multiple_dates_returns_first(self):
        """When multiple dates present, should return first match."""
        result = extract_date_from_message(
            "From December 1st to December 15th", self.ref_date
        )
        # 'from' phrase should capture December 1st
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_date_in_complex_sentence(self):
        """Should extract date from complex sentence."""
        result = extract_date_from_message(
            "I want to know what my average weight has been since December 1st please",
            self.ref_date
        )
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_invalid_date_returns_none(self):
        """Invalid date like February 30 should be handled gracefully."""
        result = extract_date_from_message("Since 2/30", self.ref_date)
        # Should return None for invalid date
        self.assertIsNone(result)

    def test_whitespace_handling(self):
        """Should handle extra whitespace."""
        result = extract_date_from_message("  since   December   1st  ", self.ref_date)
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_date_with_question_mark(self):
        """Should handle date followed by question mark."""
        result = extract_date_from_message("Weight since December 1?", self.ref_date)
        expected = datetime(2024, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)


class TestSeptemberAbbreviations(unittest.TestCase):
    """Tests for September abbreviation handling."""

    def setUp(self):
        """Set up reference date for tests."""
        self.ref_date = datetime(2024, 12, 18, 10, 30, 0)

    def test_sep_abbreviation(self):
        """Should handle 'Sep' abbreviation."""
        result = extract_date_from_message("Since Sep 15", self.ref_date)
        expected = datetime(2024, 9, 15, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_sept_abbreviation(self):
        """Should handle 'Sept' abbreviation."""
        result = extract_date_from_message("Since Sept 15", self.ref_date)
        expected = datetime(2024, 9, 15, 0, 0, 0)
        self.assertEqual(result, expected)


class TestMonthBoundaries(unittest.TestCase):
    """Tests for month boundaries and transitions."""

    def test_last_month_at_january(self):
        """'last month' in January should return December of previous year."""
        ref_date = datetime(2024, 1, 15)
        result = extract_date_from_message("My weight last month", ref_date)
        expected = datetime(2023, 12, 1, 0, 0, 0)
        self.assertEqual(result, expected)

    def test_last_week_at_month_start(self):
        """'last week' at start of month should return date in previous month."""
        ref_date = datetime(2024, 12, 2)  # Monday Dec 2
        result = extract_date_from_message("My mood last week", ref_date)
        # Last Monday would be Nov 25
        expected = datetime(2024, 11, 25, 0, 0, 0)
        self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()
