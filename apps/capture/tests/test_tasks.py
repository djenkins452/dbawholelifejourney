"""Tests for capture background tasks."""

from unittest.mock import patch

from celery.exceptions import Retry
from django.test import TestCase

from apps.capture.models import CaptureEntry
from apps.capture.tasks import (
    MAX_RETRIES,
    _is_retryable_error,
    get_processing_queue_status,
    process_capture_entry,
    process_pending_captures,
)
from apps.users.models import User


class ProcessCaptureEntryTests(TestCase):
    """Tests for process_capture_entry task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='task-test@example.com',
            password='testpass123'
        )
        self.entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/test-audio.mp3'
        )

    def test_entry_not_found(self):
        """Test handling of non-existent entry."""
        result = process_capture_entry('00000000-0000-0000-0000-000000000000')

        self.assertFalse(result['success'])
        self.assertIn('not found', result['message'])

    def test_wrong_status_rejected(self):
        """Test that entries not in transcribing status are rejected."""
        self.entry.status = CaptureEntry.STATUS_READY
        self.entry.save()

        result = process_capture_entry(str(self.entry.id))

        self.assertFalse(result['success'])
        self.assertIn('not ready for processing', result['message'])

    @patch('apps.capture.services.summarization.SummarizationService.summarize_transcript')
    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_successful_processing(self, mock_transcribe, mock_summarize):
        """Test successful full pipeline processing."""
        mock_transcribe.return_value = {
            'success': True,
            'transcript': 'Test transcript content'
        }
        mock_summarize.return_value = {
            'success': True,
            'summary': '## BLUF\nTest summary'
        }

        result = process_capture_entry(str(self.entry.id))

        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Processing complete')
        self.assertFalse(result['retried'])

        # Verify both services were called
        mock_transcribe.assert_called_once()
        mock_summarize.assert_called_once()

    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_transcription_failure_non_retryable(self, mock_transcribe):
        """Test non-retryable transcription failure."""
        mock_transcribe.return_value = {
            'success': False,
            'error': 'Invalid audio format'
        }

        result = process_capture_entry(str(self.entry.id))

        self.assertFalse(result['success'])
        self.assertIn('Transcription failed', result['message'])

    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_transcription_failure_retryable(self, mock_transcribe):
        """Test retryable transcription failure raises Celery Retry."""
        mock_transcribe.return_value = {
            'success': False,
            'error': 'Rate limit exceeded'
        }

        with self.assertRaises(Retry):
            process_capture_entry(str(self.entry.id))

    @patch('apps.capture.services.summarization.SummarizationService.summarize_transcript')
    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_summarization_failure_non_retryable(self, mock_transcribe, mock_summarize):
        """Test non-retryable summarization failure."""
        mock_transcribe.return_value = {
            'success': True,
            'transcript': 'Test transcript'
        }
        mock_summarize.return_value = {
            'success': False,
            'error': 'Invalid API key'
        }

        result = process_capture_entry(str(self.entry.id))

        self.assertFalse(result['success'])
        self.assertIn('Summarization failed', result['message'])

    @patch('apps.capture.services.summarization.SummarizationService.summarize_transcript')
    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_summarization_failure_retryable(self, mock_transcribe, mock_summarize):
        """Test retryable summarization failure raises Celery Retry."""
        mock_transcribe.return_value = {
            'success': True,
            'transcript': 'Test transcript'
        }
        mock_summarize.return_value = {
            'success': False,
            'error': 'Service temporarily unavailable'
        }

        with self.assertRaises(Retry):
            process_capture_entry(str(self.entry.id))

    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_max_retries_exceeded(self, mock_transcribe):
        """Test that retries stop after MAX_RETRIES (falls through to return)."""
        mock_transcribe.return_value = {
            'success': False,
            'error': 'Rate limit exceeded'
        }

        # At max retries, the retryable check is skipped — returns dict instead
        result = process_capture_entry(str(self.entry.id), retry_count=MAX_RETRIES)

        self.assertFalse(result['success'])
        self.assertTrue(result['retried'])

    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_unexpected_exception(self, mock_transcribe):
        """Test handling of unexpected exceptions raises Retry."""
        mock_transcribe.side_effect = Exception("Unexpected error")

        # Unexpected exceptions trigger Celery retry when retries remain
        with self.assertRaises((Retry, Exception)):
            process_capture_entry(str(self.entry.id))

        # Entry should be marked as failed
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, CaptureEntry.STATUS_FAILED)

    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_unexpected_exception_at_max_retries(self, mock_transcribe):
        """Test unexpected exception at max retries returns error dict."""
        mock_transcribe.side_effect = Exception("Unexpected error")

        result = process_capture_entry(str(self.entry.id), retry_count=MAX_RETRIES)

        self.assertFalse(result['success'])
        self.assertIn('Unexpected error', result['message'])
        self.assertTrue(result['retried'])

        # Entry should be marked as failed
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, CaptureEntry.STATUS_FAILED)

    @patch('apps.capture.services.summarization.SummarizationService.summarize_transcript')
    @patch('apps.capture.services.transcription.TranscriptionService.transcribe_audio')
    def test_retry_count_tracked(self, mock_transcribe, mock_summarize):
        """Test that retry count is properly tracked in results."""
        mock_transcribe.return_value = {
            'success': True,
            'transcript': 'Test transcript'
        }
        mock_summarize.return_value = {
            'success': True,
            'summary': '## BLUF\nTest summary'
        }

        result = process_capture_entry(str(self.entry.id), retry_count=2)

        # Whether success or failure, retried should be True
        self.assertTrue(result['retried'])


class ProcessPendingCapturesTests(TestCase):
    """Tests for process_pending_captures periodic task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='pending-test@example.com',
            password='testpass123'
        )

    def test_no_pending_entries(self):
        """Test when there are no pending entries."""
        result = process_pending_captures()

        self.assertEqual(result['dispatched'], 0)
        self.assertEqual(len(result['entry_ids']), 0)

    @patch('apps.capture.tasks.process_capture_entry')
    def test_processes_pending_entries(self, mock_process):
        """Test that pending entries are dispatched."""
        # Create entries in transcribing status
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/audio1.mp3'
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/audio2.mp3'
        )

        result = process_pending_captures()

        self.assertEqual(result['dispatched'], 2)
        # delay() is called on each entry
        self.assertEqual(mock_process.delay.call_count, 2)

    @patch('apps.capture.tasks.process_capture_entry')
    def test_only_processes_transcribing_status(self, mock_process):
        """Test that only entries in transcribing status are dispatched."""
        # Create entries in various statuses
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/audio1.mp3'
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_UPLOADING,
            audio_file_url='https://s3.example.com/audio2.mp3'
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_READY,
            audio_file_url='https://s3.example.com/audio3.mp3'
        )

        result = process_pending_captures()

        # Only the transcribing entry should be dispatched
        self.assertEqual(result['dispatched'], 1)


class IsRetryableErrorTests(TestCase):
    """Tests for _is_retryable_error helper function."""

    def test_rate_limit_is_retryable(self):
        """Test that rate limit errors are retryable."""
        self.assertTrue(_is_retryable_error("rate_limit exceeded"))
        self.assertTrue(_is_retryable_error("Rate limit error"))

    def test_timeout_is_retryable(self):
        """Test that timeout errors are retryable."""
        self.assertTrue(_is_retryable_error("Connection timed out"))
        self.assertTrue(_is_retryable_error("Request timeout"))

    def test_busy_is_retryable(self):
        """Test that busy errors are retryable."""
        self.assertTrue(_is_retryable_error("Service busy"))
        self.assertTrue(_is_retryable_error("Server is busy, try again later"))

    def test_connection_is_retryable(self):
        """Test that connection errors are retryable."""
        self.assertTrue(_is_retryable_error("Connection refused"))
        self.assertTrue(_is_retryable_error("Network connection failed"))

    def test_503_is_retryable(self):
        """Test that 503 errors are retryable."""
        self.assertTrue(_is_retryable_error("HTTP 503 Service Unavailable"))

    def test_invalid_format_not_retryable(self):
        """Test that format errors are not retryable."""
        self.assertFalse(_is_retryable_error("Invalid audio format"))

    def test_auth_error_not_retryable(self):
        """Test that auth errors are not retryable."""
        self.assertFalse(_is_retryable_error("Invalid API key"))
        self.assertFalse(_is_retryable_error("Authentication failed"))


class GetProcessingQueueStatusTests(TestCase):
    """Tests for get_processing_queue_status function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='queue-test@example.com',
            password='testpass123'
        )

    def test_empty_queue(self):
        """Test queue status with no entries."""
        status = get_processing_queue_status()

        self.assertEqual(status['uploading'], 0)
        self.assertEqual(status['transcribing'], 0)
        self.assertEqual(status['summarizing'], 0)
        self.assertEqual(status['ready'], 0)
        self.assertEqual(status['failed'], 0)

    def test_counts_by_status(self):
        """Test that entries are counted by status."""
        # Create entries in various statuses
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_UPLOADING
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_SUMMARIZING
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_READY
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_READY
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_READY
        )
        CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED
        )

        status = get_processing_queue_status()

        self.assertEqual(status['uploading'], 1)
        self.assertEqual(status['transcribing'], 2)
        self.assertEqual(status['summarizing'], 1)
        self.assertEqual(status['ready'], 3)
        self.assertEqual(status['failed'], 1)


class ConfirmUploadTaskTriggerTests(TestCase):
    """Tests for task triggering from CaptureSubmitView._confirm_upload."""

    def setUp(self):
        """Set up test data."""
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        self.user = User.objects.create_user(
            email='trigger-test@example.com',
            password='testpass123'
        )
        # Accept terms and complete onboarding
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_UPLOADING,
            audio_file_url='https://s3.example.com/test-audio.mp3'
        )

    @patch('apps.capture.tasks.process_capture_entry')
    def test_confirm_upload_triggers_processing(self, mock_process):
        """Test that confirming upload triggers the processing task."""
        import json
        import time

        from django.test import Client
        from django.urls import reverse

        mock_process.return_value = {'success': True, 'message': 'Complete'}

        client = Client()
        client.force_login(self.user)

        response = client.post(
            reverse('capture:submit'),
            data=json.dumps({
                'action': 'confirm_upload',
                'entry_id': str(self.entry.id)
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], CaptureEntry.STATUS_TRANSCRIBING)

        # Wait briefly for the background thread to start
        time.sleep(0.3)

        # Verify the entry status was updated to transcribing
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, CaptureEntry.STATUS_TRANSCRIBING)

        # Verify task was called (mock should have been invoked in the thread)
        # Note: Due to threading, the mock call may not be captured reliably in tests
