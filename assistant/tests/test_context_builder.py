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


class TestBuildPersonalContextFoodOnly(unittest.TestCase):
    """Tests for build_personal_context with food data only."""

    def test_formats_food_data(self):
        """Should format food data correctly."""
        from assistant.context_builder import build_personal_context

        data = {
            'food': {
                'type': 'food',
                'total_entries': 45,
                'total_calories': 67500.0,
                'average_daily_calories': 1875.0,
                'latest_date': date(2024, 12, 18),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Food Data:', result)
        self.assertIn('Total entries: 45', result)
        self.assertIn('Total calories: 67500.0', result)
        self.assertIn('Average daily calories: 1875.0', result)
        self.assertIn('Most recent entry: 2024-12-18', result)

    def test_includes_header_and_footer(self):
        """Should include header and closing instruction."""
        from assistant.context_builder import build_personal_context

        data = {
            'food': {
                'type': 'food',
                'total_entries': 10,
                'total_calories': 15000.0,
                'average_daily_calories': 1500.0,
                'latest_date': date(2024, 12, 15),
            }
        }

        result = build_personal_context(data)
        self.assertIn("user's personal data", result)
        self.assertIn('personalized, helpful responses', result)


class TestBuildPersonalContextMoodOnly(unittest.TestCase):
    """Tests for build_personal_context with mood data only."""

    def test_formats_mood_data(self):
        """Should format mood data correctly."""
        from assistant.context_builder import build_personal_context

        data = {
            'mood': {
                'type': 'mood',
                'count': 15,
                'mood_distribution': {'great': 3, 'good': 7, 'okay': 4, 'low': 1},
                'most_common': 'good',
                'latest_mood': 'good',
                'latest_date': date(2024, 12, 18),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Mood Data:', result)
        self.assertIn('Total mood entries: 15', result)
        self.assertIn('Most common mood: good', result)
        self.assertIn('Mood breakdown:', result)
        self.assertIn('Most recent: good on 2024-12-18', result)

    def test_formats_mood_distribution(self):
        """Should format mood distribution breakdown."""
        from assistant.context_builder import build_personal_context

        data = {
            'mood': {
                'type': 'mood',
                'count': 10,
                'mood_distribution': {'great': 5, 'good': 3, 'okay': 2},
                'most_common': 'great',
                'latest_mood': 'great',
                'latest_date': date(2024, 12, 17),
            }
        }

        result = build_personal_context(data)

        # Check that all moods appear in the breakdown
        self.assertIn('great:', result)
        self.assertIn('good:', result)
        self.assertIn('okay:', result)


class TestFormatFoodData(unittest.TestCase):
    """Tests for _format_food_data helper function."""

    def test_returns_empty_string_for_empty_data(self):
        """Should return empty string for empty dict."""
        from assistant.context_builder import _format_food_data

        result = _format_food_data({})
        self.assertEqual(result, '')

    def test_returns_empty_string_for_none(self):
        """Should return empty string for None."""
        from assistant.context_builder import _format_food_data

        result = _format_food_data(None)
        self.assertEqual(result, '')

    def test_formats_complete_food_data(self):
        """Should format all food data fields."""
        from assistant.context_builder import _format_food_data

        data = {
            'type': 'food',
            'total_entries': 30,
            'total_calories': 45000.0,
            'average_daily_calories': 1500.0,
            'latest_date': date(2024, 12, 16),
        }

        result = _format_food_data(data)

        self.assertIn('Food Data:', result)
        self.assertIn('Total entries: 30', result)
        self.assertIn('Total calories: 45000.0', result)
        self.assertIn('Average daily calories: 1500.0', result)
        self.assertIn('Most recent entry: 2024-12-16', result)


class TestFormatMoodData(unittest.TestCase):
    """Tests for _format_mood_data helper function."""

    def test_returns_empty_string_for_empty_data(self):
        """Should return empty string for empty dict."""
        from assistant.context_builder import _format_mood_data

        result = _format_mood_data({})
        self.assertEqual(result, '')

    def test_returns_empty_string_for_none(self):
        """Should return empty string for None."""
        from assistant.context_builder import _format_mood_data

        result = _format_mood_data(None)
        self.assertEqual(result, '')

    def test_formats_complete_mood_data(self):
        """Should format all mood data fields."""
        from assistant.context_builder import _format_mood_data

        data = {
            'type': 'mood',
            'count': 20,
            'mood_distribution': {'great': 8, 'good': 10, 'okay': 2},
            'most_common': 'good',
            'latest_mood': 'great',
            'latest_date': date(2024, 12, 18),
        }

        result = _format_mood_data(data)

        self.assertIn('Mood Data:', result)
        self.assertIn('Total mood entries: 20', result)
        self.assertIn('Most common mood: good', result)
        self.assertIn('Mood breakdown:', result)
        self.assertIn('Most recent: great on 2024-12-18', result)


class TestBuildPersonalContextAllFiveTypes(unittest.TestCase):
    """Tests for build_personal_context with all five data types."""

    def test_formats_all_five_types(self):
        """Should format weight, journal, medication, food, and mood data."""
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
            },
            'food': {
                'type': 'food',
                'total_entries': 25,
                'total_calories': 50000.0,
                'average_daily_calories': 2000.0,
                'latest_date': date(2024, 12, 18),
            },
            'mood': {
                'type': 'mood',
                'count': 12,
                'mood_distribution': {'good': 6, 'great': 4, 'okay': 2},
                'most_common': 'good',
                'latest_mood': 'great',
                'latest_date': date(2024, 12, 18),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Weight Data:', result)
        self.assertIn('Journal Data:', result)
        self.assertIn('Medication Data:', result)
        self.assertIn('Food Data:', result)
        self.assertIn('Mood Data:', result)

    def test_formats_food_and_mood_together(self):
        """Should format food and mood data together."""
        from assistant.context_builder import build_personal_context

        data = {
            'food': {
                'type': 'food',
                'total_entries': 15,
                'total_calories': 30000.0,
                'average_daily_calories': 2000.0,
                'latest_date': date(2024, 12, 17),
            },
            'mood': {
                'type': 'mood',
                'count': 7,
                'mood_distribution': {'great': 4, 'good': 3},
                'most_common': 'great',
                'latest_mood': 'good',
                'latest_date': date(2024, 12, 18),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Food Data:', result)
        self.assertIn('Mood Data:', result)
        # Verify sections are separated
        self.assertIn('\n\n', result)

    def test_formats_weight_food_mood(self):
        """Should format weight, food, and mood data together."""
        from assistant.context_builder import build_personal_context

        data = {
            'weight': {
                'type': 'weight',
                'count': 5,
                'average': 170.0,
                'latest': 169.5,
                'latest_date': date(2024, 12, 16),
                'unit': 'kg',
            },
            'food': {
                'type': 'food',
                'total_entries': 20,
                'total_calories': 40000.0,
                'average_daily_calories': 2000.0,
                'latest_date': date(2024, 12, 17),
            },
            'mood': {
                'type': 'mood',
                'count': 5,
                'mood_distribution': {'good': 5},
                'most_common': 'good',
                'latest_mood': 'good',
                'latest_date': date(2024, 12, 17),
            }
        }

        result = build_personal_context(data)

        self.assertIn('Weight Data:', result)
        self.assertIn('Food Data:', result)
        self.assertIn('Mood Data:', result)


class TestBuildPersonalContextGlucoseOnly(unittest.TestCase):
    """Tests for build_personal_context with glucose data only."""

    def test_formats_glucose_data(self):
        """Should format glucose data correctly."""
        from assistant.context_builder import build_personal_context

        data = {
            'glucose': {
                'type': 'glucose',
                'count': 100,
                'average': 118.5,
                'latest': 115.0,
                'latest_date': datetime(2024, 12, 18, 8, 30),
                'unit': 'mg/dL',
            }
        }

        result = build_personal_context(data)

        self.assertIn('Glucose Data:', result)
        self.assertIn('Total entries: 100', result)
        self.assertIn('Average: 118.5 mg/dL', result)
        self.assertIn('Most recent: 115.0 mg/dL on 2024-12-18', result)

    def test_includes_header_and_footer(self):
        """Should include header and closing instruction."""
        from assistant.context_builder import build_personal_context

        data = {
            'glucose': {
                'type': 'glucose',
                'count': 50,
                'average': 120.0,
                'latest': 118.0,
                'latest_date': date(2024, 12, 15),
                'unit': 'mmol/L',
            }
        }

        result = build_personal_context(data)
        self.assertIn("user's personal data", result)
        self.assertIn('personalized, helpful responses', result)


class TestFormatGlucoseData(unittest.TestCase):
    """Tests for _format_glucose_data helper function."""

    def test_returns_empty_string_for_empty_data(self):
        """Should return empty string for empty dict."""
        from assistant.context_builder import _format_glucose_data

        result = _format_glucose_data({})
        self.assertEqual(result, '')

    def test_returns_empty_string_for_none(self):
        """Should return empty string for None."""
        from assistant.context_builder import _format_glucose_data

        result = _format_glucose_data(None)
        self.assertEqual(result, '')

    def test_formats_complete_glucose_data(self):
        """Should format all glucose data fields."""
        from assistant.context_builder import _format_glucose_data

        data = {
            'type': 'glucose',
            'count': 200,
            'average': 125.5,
            'latest': 120.0,
            'latest_date': datetime(2024, 12, 16, 7, 45),
            'unit': 'mg/dL',
        }

        result = _format_glucose_data(data)

        self.assertIn('Glucose Data:', result)
        self.assertIn('Total entries: 200', result)
        self.assertIn('Average: 125.5 mg/dL', result)
        self.assertIn('Most recent: 120.0 mg/dL on 2024-12-16', result)


class TestBuildPersonalContextWithGlucose(unittest.TestCase):
    """Tests for build_personal_context including glucose with other types."""

    def test_formats_glucose_and_weight(self):
        """Should format both glucose and weight data."""
        from assistant.context_builder import build_personal_context

        data = {
            'glucose': {
                'type': 'glucose',
                'count': 50,
                'average': 115.0,
                'latest': 110.0,
                'latest_date': date(2024, 12, 18),
                'unit': 'mg/dL',
            },
            'weight': {
                'type': 'weight',
                'count': 10,
                'average': 175.0,
                'latest': 174.5,
                'latest_date': date(2024, 12, 18),
                'unit': 'lb',
            }
        }

        result = build_personal_context(data)

        self.assertIn('Glucose Data:', result)
        self.assertIn('Weight Data:', result)

    def test_formats_all_six_types(self):
        """Should format all six data types including glucose."""
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
            },
            'food': {
                'type': 'food',
                'total_entries': 25,
                'total_calories': 50000.0,
                'average_daily_calories': 2000.0,
                'latest_date': date(2024, 12, 18),
            },
            'mood': {
                'type': 'mood',
                'count': 12,
                'mood_distribution': {'good': 6, 'great': 4, 'okay': 2},
                'most_common': 'good',
                'latest_mood': 'great',
                'latest_date': date(2024, 12, 18),
            },
            'glucose': {
                'type': 'glucose',
                'count': 100,
                'average': 120.0,
                'latest': 115.0,
                'latest_date': date(2024, 12, 18),
                'unit': 'mg/dL',
            }
        }

        result = build_personal_context(data)

        self.assertIn('Weight Data:', result)
        self.assertIn('Journal Data:', result)
        self.assertIn('Medication Data:', result)
        self.assertIn('Food Data:', result)
        self.assertIn('Mood Data:', result)
        self.assertIn('Glucose Data:', result)


if __name__ == '__main__':
    unittest.main()
