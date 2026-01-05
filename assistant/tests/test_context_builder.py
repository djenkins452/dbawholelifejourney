"""
Unit tests for the Context Builder.

Tests cover build_personal_context() function with various data combinations.
"""

import unittest
from datetime import date, datetime


class TestBuildPersonalContextEmpty(unittest.TestCase):
    """Tests for build_personal_context when no data exists."""

    def test_returns_empty_string_for_none(self):
        """Should return empty string when data_results is None."""
        from assistant.context_builder import build_personal_context

        result = build_personal_context(None)
        self.assertEqual(result, '')

    def test_returns_empty_string_for_empty_dict(self):
        """Should return empty string when data_results is empty dict."""
        from assistant.context_builder import build_personal_context

        result = build_personal_context({})
        self.assertEqual(result, '')


class TestBuildPersonalContextWeightOnly(unittest.TestCase):
    """Tests for build_personal_context with weight data only."""

    def test_formats_weight_data(self):
        """Should format weight data correctly."""
        from assistant.context_builder import build_personal_context

        data = {
            'weight': {
                'type': 'weight',
                'count': 15,
                'average': 175.5,
                'latest': 174.0,
                'latest_date': datetime(2024, 12, 18, 8, 30),
                'unit': 'lb',
            }
        }

        result = build_personal_context(data)

        self.assertIn("user's personal data", result)
        self.assertIn('Weight Data:', result)
        self.assertIn('Total entries: 15', result)
        self.assertIn('Average: 175.5 lb', result)
        self.assertIn('Most recent: 174.0 lb on 2024-12-18', result)

    def test_includes_closing_instruction(self):
        """Should include closing instruction for AI."""
        from assistant.context_builder import build_personal_context

        data = {
            'weight': {
                'type': 'weight',
                'count': 5,
                'average': 170.0,
                'latest': 169.5,
                'latest_date': date(2024, 12, 15),
                'unit': 'kg',
            }
        }

        result = build_personal_context(data)
        self.assertIn('personalized, helpful responses', result)


class TestBuildPersonalContextJournalOnly(unittest.TestCase):
    """Tests for build_personal_context with journal data only."""

    def test_formats_journal_data(self):
        """Should format journal data correctly."""
        from assistant.context_builder import build_personal_context

        data = {
            'journal': {
                'type': 'journal',
                'count': 10,
                'latest_date': date(2024, 12, 17),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Journal Data:', result)
        self.assertIn('Total entries: 10', result)
        self.assertIn('Most recent entry: 2024-12-17', result)


class TestBuildPersonalContextMedicationOnly(unittest.TestCase):
    """Tests for build_personal_context with medication data only."""

    def test_formats_medication_data(self):
        """Should format medication data correctly."""
        from assistant.context_builder import build_personal_context

        data = {
            'medication': {
                'type': 'medication',
                'total_logs': 45,
                'days_logged': 15,
                'total_days': 18,
                'consistency_percent': 83.3,
            }
        }

        result = build_personal_context(data)

        self.assertIn('Medication Data:', result)
        self.assertIn('Total medication logs: 45', result)
        self.assertIn('Days with logs: 15 out of 18 days', result)
        self.assertIn('Consistency: 83.3%', result)


class TestBuildPersonalContextMultipleTypes(unittest.TestCase):
    """Tests for build_personal_context with multiple data types."""

    def test_formats_weight_and_journal(self):
        """Should format both weight and journal data."""
        from assistant.context_builder import build_personal_context

        data = {
            'weight': {
                'type': 'weight',
                'count': 10,
                'average': 175.0,
                'latest': 174.5,
                'latest_date': date(2024, 12, 18),
                'unit': 'lb',
            },
            'journal': {
                'type': 'journal',
                'count': 8,
                'latest_date': date(2024, 12, 17),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Weight Data:', result)
        self.assertIn('Journal Data:', result)

    def test_formats_all_three_types(self):
        """Should format weight, journal, and medication data."""
        from assistant.context_builder import build_personal_context

        data = {
            'weight': {
                'type': 'weight',
                'count': 10,
                'average': 175.0,
                'latest': 174.5,
                'latest_date': date(2024, 12, 18),
                'unit': 'lb',
            },
            'journal': {
                'type': 'journal',
                'count': 8,
                'latest_date': date(2024, 12, 17),
            },
            'medication': {
                'type': 'medication',
                'total_logs': 30,
                'days_logged': 10,
                'total_days': 14,
                'consistency_percent': 71.4,
            }
        }

        result = build_personal_context(data)

        self.assertIn('Weight Data:', result)
        self.assertIn('Journal Data:', result)
        self.assertIn('Medication Data:', result)
        # All sections should be separated by blank lines
        self.assertIn('\n\n', result)


class TestFormatDateHelper(unittest.TestCase):
    """Tests for _format_date helper function."""

    def test_formats_datetime(self):
        """Should format datetime object to YYYY-MM-DD."""
        from assistant.context_builder import _format_date

        dt = datetime(2024, 12, 18, 14, 30, 45)
        result = _format_date(dt)
        self.assertEqual(result, '2024-12-18')

    def test_formats_date(self):
        """Should format date object to YYYY-MM-DD."""
        from assistant.context_builder import _format_date

        d = date(2024, 12, 17)
        result = _format_date(d)
        self.assertEqual(result, '2024-12-17')

    def test_handles_string_fallback(self):
        """Should convert unknown types to string."""
        from assistant.context_builder import _format_date

        result = _format_date('2024-12-16')
        self.assertEqual(result, '2024-12-16')


class TestFormatWeightData(unittest.TestCase):
    """Tests for _format_weight_data helper function."""

    def test_returns_empty_string_for_empty_data(self):
        """Should return empty string for empty dict."""
        from assistant.context_builder import _format_weight_data

        result = _format_weight_data({})
        self.assertEqual(result, '')

    def test_returns_empty_string_for_none(self):
        """Should return empty string for None."""
        from assistant.context_builder import _format_weight_data

        result = _format_weight_data(None)
        self.assertEqual(result, '')


class TestFormatJournalData(unittest.TestCase):
    """Tests for _format_journal_data helper function."""

    def test_returns_empty_string_for_empty_data(self):
        """Should return empty string for empty dict."""
        from assistant.context_builder import _format_journal_data

        result = _format_journal_data({})
        self.assertEqual(result, '')


class TestFormatMedicationData(unittest.TestCase):
    """Tests for _format_medication_data helper function."""

    def test_returns_empty_string_for_empty_data(self):
        """Should return empty string for empty dict."""
        from assistant.context_builder import _format_medication_data

        result = _format_medication_data({})
        self.assertEqual(result, '')


if __name__ == '__main__':
    unittest.main()
