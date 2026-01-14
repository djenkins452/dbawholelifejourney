"""Tests for capture summarization service."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.capture.models import CaptureEntry
from apps.capture.services.summarization import (
    BLUF_SYSTEM_PROMPT,
    SummarizationError,
    SummarizationService,
)
from apps.users.models import User


class SummarizationServiceInitializationTests(TestCase):
    """Tests for SummarizationService initialization."""

    @override_settings(OPENAI_API_KEY='test-api-key')
    @patch('openai.OpenAI')
    def test_service_initializes_with_api_key(self, mock_openai):
        """Test service initializes client when API key is configured."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        service = SummarizationService()

        self.assertTrue(service.is_available)
        mock_openai.assert_called_once_with(api_key='test-api-key')

    @override_settings(OPENAI_API_KEY=None)
    def test_service_not_available_without_api_key(self):
        """Test service is not available when API key is not configured."""
        service = SummarizationService()

        self.assertFalse(service.is_available)

    @override_settings(OPENAI_API_KEY='')
    def test_service_not_available_with_empty_api_key(self):
        """Test service is not available when API key is empty."""
        service = SummarizationService()

        self.assertFalse(service.is_available)

    @override_settings(OPENAI_API_KEY='test-api-key', OPENAI_MODEL='gpt-4')
    @patch('openai.OpenAI')
    def test_service_uses_configured_model(self, mock_openai):
        """Test service uses the model from settings."""
        service = SummarizationService()
        self.assertEqual(service.model, 'gpt-4')


@override_settings(OPENAI_API_KEY='test-api-key')
class SummarizationServiceSummarizeTests(TestCase):
    """Tests for SummarizationService.summarize_transcript method."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.capture_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_SUMMARIZING,
            transcript="This is a test transcript about faith and spiritual growth."
        )

    @patch('openai.OpenAI')
    def test_summarize_transcript_success(self, mock_openai):
        """Test successful transcript summarization."""
        # Mock OpenAI API response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """## BLUF (Bottom Line Up Front)
This is a test summary about faith and spiritual growth.

## Key Points
- Point 1
- Point 2

## Scripture References
No scripture references found in this recording.

## Action Items
No specific action items identified.

## Notable Quotes
No notable quotes identified.

## Detailed Notes
This is the detailed notes section."""

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertTrue(result['success'])
        self.assertIn('BLUF', result['summary'])

        # Verify entry was updated
        self.capture_entry.refresh_from_db()
        self.assertIn('BLUF', self.capture_entry.summary)
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_READY)
        self.assertEqual(self.capture_entry.error_message, '')

    @patch('openai.OpenAI')
    def test_summarize_transcript_no_transcript(self, mock_openai):
        """Test summarization fails gracefully when no transcript."""
        mock_openai.return_value = MagicMock()

        self.capture_entry.transcript = ''
        self.capture_entry.save()

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('No transcript', result['error'])

        # Verify entry was marked as failed
        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('No transcript', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    def test_summarize_transcript_empty_response(self, mock_openai):
        """Test summarization handles empty response from API."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('empty summary', result['error'].lower())

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)

    @patch('openai.OpenAI')
    def test_summarize_transcript_api_rate_limit(self, mock_openai):
        """Test summarization handles rate limit error."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("rate_limit exceeded")
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('busy', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    def test_summarize_transcript_api_auth_error(self, mock_openai):
        """Test summarization handles authentication error."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("invalid_api_key")
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('temporarily unavailable', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    def test_summarize_transcript_context_length_error(self, mock_openai):
        """Test summarization handles context length error."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("context_length_exceeded")
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('too long', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    def test_summarize_transcript_generic_error(self, mock_openai):
        """Test summarization handles generic API error."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Unknown error occurred")
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('try again', self.capture_entry.error_message.lower())


@override_settings(OPENAI_API_KEY='test-api-key')
class SummarizationServiceTruncationTests(TestCase):
    """Tests for transcript truncation handling."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='truncation-test@example.com',
            password='testpass123'
        )

    @patch('openai.OpenAI')
    def test_long_transcript_is_truncated(self, mock_openai):
        """Test that very long transcripts are truncated."""
        # Create a transcript longer than 100k characters
        long_transcript = "Word " * 25000  # ~125k characters

        capture_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_SUMMARIZING,
            transcript=long_transcript
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## BLUF\nSummary of truncated content."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(capture_entry)

        self.assertTrue(result['success'])

        # Verify the API was called with truncated content
        call_args = mock_client.chat.completions.create.call_args
        user_message = call_args.kwargs['messages'][1]['content']
        self.assertIn('[Transcript truncated due to length]', user_message)

    @patch('openai.OpenAI')
    def test_short_transcript_not_truncated(self, mock_openai):
        """Test that short transcripts are not truncated."""
        short_transcript = "This is a short transcript."

        capture_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_SUMMARIZING,
            transcript=short_transcript
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## BLUF\nShort summary."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = SummarizationService()
        result = service.summarize_transcript(capture_entry)

        self.assertTrue(result['success'])

        # Verify the API was called without truncation marker
        call_args = mock_client.chat.completions.create.call_args
        user_message = call_args.kwargs['messages'][1]['content']
        self.assertNotIn('[Transcript truncated', user_message)


class SummarizationErrorTests(TestCase):
    """Tests for SummarizationError exception."""

    def test_error_with_user_message(self):
        """Test SummarizationError stores both messages."""
        error = SummarizationError(
            "Technical error details",
            "User-friendly message"
        )

        self.assertEqual(str(error), "Technical error details")
        self.assertEqual(error.user_message, "User-friendly message")

    def test_error_without_user_message(self):
        """Test SummarizationError uses main message as user message."""
        error = SummarizationError("Error message")

        self.assertEqual(str(error), "Error message")
        self.assertEqual(error.user_message, "Error message")


class SummarizationServiceNotAvailableTests(TestCase):
    """Tests for service behavior when not available."""

    @override_settings(OPENAI_API_KEY=None)
    def test_summarize_returns_error_when_not_available(self):
        """Test summarize_transcript returns error when service not available."""
        user = User.objects.create_user(
            email='unavailable-test@example.com',
            password='testpass123'
        )
        capture_entry = CaptureEntry.objects.create(
            user=user,
            status=CaptureEntry.STATUS_SUMMARIZING,
            transcript="Test transcript"
        )

        service = SummarizationService()
        result = service.summarize_transcript(capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('not available', result['error'].lower())

        capture_entry.refresh_from_db()
        self.assertEqual(capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('temporarily unavailable', capture_entry.error_message)


class BLUFPromptTests(TestCase):
    """Tests for BLUF prompt configuration."""

    def test_bluf_system_prompt_has_required_sections(self):
        """Test that BLUF system prompt includes all required sections."""
        required_sections = [
            'BLUF',
            'Key Points',
            'Scripture References',
            'Action Items',
            'Notable Quotes',
            'Detailed Notes'
        ]

        for section in required_sections:
            self.assertIn(section, BLUF_SYSTEM_PROMPT, f"Missing section: {section}")

    def test_bluf_system_prompt_has_guidelines(self):
        """Test that BLUF system prompt includes summarization guidelines."""
        self.assertIn('Guidelines', BLUF_SYSTEM_PROMPT)
        self.assertIn('concise', BLUF_SYSTEM_PROMPT.lower())
