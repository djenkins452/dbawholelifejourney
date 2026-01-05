"""
Unit tests for the Assistant Views.

Tests cover process_assistant_message() function with various scenarios.
"""

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch


class TestProcessAssistantMessageNonPersonalQuery(unittest.TestCase):
    """Tests for process_assistant_message when query is not personal."""

    def test_returns_base_prompt_for_non_personal_query(self):
        """Should return base prompt unchanged for non-personal queries."""
        from assistant.views import process_assistant_message

        user = MagicMock()
        message = "What is the weather like today?"
        base_prompt = "You are a helpful assistant."

        result = process_assistant_message(user, message, base_prompt)

        self.assertEqual(result['system_prompt'], base_prompt)
        self.assertFalse(result['is_personal_query'])
        self.assertEqual(result['data_types'], [])
        self.assertFalse(result['has_data'])

    def test_returns_empty_prompt_when_no_base_prompt(self):
        """Should return empty prompt when no base prompt provided."""
        from assistant.views import process_assistant_message

        user = MagicMock()
        message = "Hello, how are you?"

        result = process_assistant_message(user, message)

        self.assertEqual(result['system_prompt'], "")
        self.assertFalse(result['is_personal_query'])

    def test_handles_empty_message(self):
        """Should handle empty message gracefully."""
        from assistant.views import process_assistant_message

        user = MagicMock()

        result = process_assistant_message(user, "", "Base prompt")

        self.assertEqual(result['system_prompt'], "Base prompt")
        self.assertFalse(result['is_personal_query'])


class TestProcessAssistantMessagePersonalQueryNoData(unittest.TestCase):
    """Tests for personal queries when no data exists."""

    @patch('assistant.views.PersonalDataService')
    def test_returns_base_prompt_when_no_data(self, mock_service_class):
        """Should return base prompt when user has no matching data."""
        from assistant.views import process_assistant_message

        # Mock service to return None (no data)
        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = None
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "What was my weight last week?"
        base_prompt = "You are helpful."

        result = process_assistant_message(user, message, base_prompt)

        self.assertEqual(result['system_prompt'], base_prompt)
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertFalse(result['has_data'])


class TestProcessAssistantMessageWithWeightData(unittest.TestCase):
    """Tests for personal queries with weight data."""

    @patch('assistant.views.PersonalDataService')
    def test_appends_weight_context_to_prompt(self, mock_service_class):
        """Should append weight data context to system prompt."""
        from assistant.views import process_assistant_message

        # Mock service to return weight data
        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
            'weight': {
                'type': 'weight',
                'count': 10,
                'average': 175.0,
                'latest': 174.5,
                'latest_date': date(2024, 12, 18),
                'unit': 'lb',
            }
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "What is my average weight?"
        base_prompt = "You are helpful."

        result = process_assistant_message(user, message, base_prompt)

        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['has_data'])
        self.assertIn("You are helpful.", result['system_prompt'])
        self.assertIn("Weight Data:", result['system_prompt'])
        self.assertIn("175.0 lb", result['system_prompt'])

    @patch('assistant.views.PersonalDataService')
    def test_works_without_base_prompt(self, mock_service_class):
        """Should work without base prompt."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
            'weight': {
                'type': 'weight',
                'count': 5,
                'average': 170.0,
                'latest': 169.0,
                'latest_date': date(2024, 12, 17),
                'unit': 'kg',
            }
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "Show my weight data"

        result = process_assistant_message(user, message)

        self.assertIn("Weight Data:", result['system_prompt'])
        self.assertNotIn("None", result['system_prompt'])


class TestProcessAssistantMessageWithJournalData(unittest.TestCase):
    """Tests for personal queries with journal data."""

    @patch('assistant.views.PersonalDataService')
    def test_appends_journal_context_to_prompt(self, mock_service_class):
        """Should append journal data context to system prompt."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
            'journal': {
                'type': 'journal',
                'count': 15,
                'latest_date': date(2024, 12, 18),
            }
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "How many journal entries do I have?"
        base_prompt = "Assistant prompt."

        result = process_assistant_message(user, message, base_prompt)

        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['has_data'])
        self.assertIn("Journal Data:", result['system_prompt'])
        self.assertIn("Total entries: 15", result['system_prompt'])


class TestProcessAssistantMessageWithMedicationData(unittest.TestCase):
    """Tests for personal queries with medication data."""

    @patch('assistant.views.PersonalDataService')
    def test_appends_medication_context_to_prompt(self, mock_service_class):
        """Should append medication data context to system prompt."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
            'medication': {
                'type': 'medication',
                'total_logs': 30,
                'days_logged': 10,
                'total_days': 14,
                'consistency_percent': 71.4,
            }
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "Have I been taking my medications?"
        base_prompt = "You are a wellness coach."

        result = process_assistant_message(user, message, base_prompt)

        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['has_data'])
        self.assertIn("Medication Data:", result['system_prompt'])
        self.assertIn("Consistency: 71.4%", result['system_prompt'])


class TestProcessAssistantMessageMultipleDataTypes(unittest.TestCase):
    """Tests for personal queries with multiple data types."""

    @patch('assistant.views.PersonalDataService')
    def test_handles_multiple_data_types(self, mock_service_class):
        """Should handle queries about multiple data types."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
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
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "Tell me about my weight and journal entries"

        result = process_assistant_message(user, message)

        self.assertTrue(result['has_data'])
        self.assertIn("Weight Data:", result['system_prompt'])
        self.assertIn("Journal Data:", result['system_prompt'])


class TestProcessAssistantMessageDateExtraction(unittest.TestCase):
    """Tests for date extraction in personal queries."""

    @patch('assistant.views.PersonalDataService')
    @patch('assistant.views.extract_date_from_message')
    def test_passes_extracted_date_to_service(self, mock_extract, mock_service_class):
        """Should pass extracted date to data service."""
        from assistant.views import process_assistant_message

        # Mock date extraction to return specific date
        extracted_date = datetime(2024, 12, 1)
        mock_extract.return_value = extracted_date

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
            'weight': {
                'type': 'weight',
                'count': 5,
                'average': 175.0,
                'latest': 174.0,
                'latest_date': date(2024, 12, 15),
                'unit': 'lb',
            }
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        message = "What was my weight since December 1st?"

        result = process_assistant_message(user, message)

        # Verify extract_date_from_message was called
        mock_extract.assert_called_once_with(message)

        # Verify query_by_intent was called with the extracted date
        mock_service.query_by_intent.assert_called_once()
        call_kwargs = mock_service.query_by_intent.call_args[1]
        self.assertEqual(call_kwargs['since_date'], extracted_date)

    @patch('assistant.views.PersonalDataService')
    @patch('assistant.views.extract_date_from_message')
    def test_no_date_extraction_without_date_context(self, mock_extract, mock_service_class):
        """Should not extract date when no date context detected."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = {
            'weight': {
                'type': 'weight',
                'count': 5,
                'average': 175.0,
                'latest': 174.0,
                'latest_date': date(2024, 12, 15),
                'unit': 'lb',
            }
        }
        mock_service_class.return_value = mock_service

        user = MagicMock()
        # Message without date context (no 'last', 'since', etc.)
        message = "What is my weight?"

        result = process_assistant_message(user, message)

        # Verify query was called with None for since_date
        call_kwargs = mock_service.query_by_intent.call_args[1]
        self.assertIsNone(call_kwargs['since_date'])


class TestProcessAssistantMessageUnsupportedDataTypes(unittest.TestCase):
    """Tests for queries with unsupported data types."""

    @patch('assistant.views.PersonalDataService')
    def test_filters_unsupported_data_types(self, mock_service_class):
        """Should filter out unsupported data types before querying."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = None
        mock_service_class.return_value = mock_service

        user = MagicMock()
        # 'mood' is detected but not supported yet
        message = "How has my mood been lately?"
        base_prompt = "Assistant."

        result = process_assistant_message(user, message, base_prompt)

        # Should still detect as personal query
        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])

        # But query_by_intent should not be called since mood is unsupported
        # (no supported types to query)
        self.assertFalse(mock_service.query_by_intent.called)


class TestProcessAssistantMessageServiceInitialization(unittest.TestCase):
    """Tests for PersonalDataService initialization."""

    @patch('assistant.views.PersonalDataService')
    def test_initializes_service_with_user(self, mock_service_class):
        """Should initialize PersonalDataService with the provided user."""
        from assistant.views import process_assistant_message

        mock_service = MagicMock()
        mock_service.query_by_intent.return_value = None
        mock_service_class.return_value = mock_service

        user = MagicMock()
        user.id = 42
        message = "What is my weight?"

        process_assistant_message(user, message)

        # Verify service was initialized with user
        mock_service_class.assert_called_once_with(user)


if __name__ == '__main__':
    unittest.main()
