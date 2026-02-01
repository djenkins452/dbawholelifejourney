"""Tests for error handling and retry functionality in Capture feature."""

from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.capture.models import CaptureEntry
from apps.users.models import TermsAcceptance

User = get_user_model()


def create_test_user(email='test@example.com', password='testpass123'):
    """Create a test user with terms accepted and onboarding completed."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class CaptureEntryErrorTypeTests(TestCase):
    """Tests for CaptureEntry error type detection methods."""

    def setUp(self):
        self.user = create_test_user()

    def test_get_error_type_mic_denied(self):
        """Test detection of microphone denied errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Microphone access was denied by the user'
        )
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_MIC_DENIED)

        entry.error_message = 'Permission denied for mic'
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_MIC_DENIED)

    def test_get_error_type_upload_failed(self):
        """Test detection of upload failure errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Upload to S3 failed: connection timeout'
        )
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_UPLOAD_FAILED)

        entry.error_message = 'Storage error: bucket not accessible'
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_UPLOAD_FAILED)

    def test_get_error_type_transcription_failed(self):
        """Test detection of transcription failure errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed: audio quality too low'
        )
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_TRANSCRIPTION_FAILED)

        entry.error_message = 'Whisper API error: invalid audio format'
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_TRANSCRIPTION_FAILED)

        entry.error_message = 'Speech recognition service unavailable'
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_TRANSCRIPTION_FAILED)

    def test_get_error_type_summarization_failed(self):
        """Test detection of summarization failure errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Summarization failed: OpenAI rate limit exceeded'
        )
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_SUMMARIZATION_FAILED)

        entry.error_message = 'Summary generation error: content too long'
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_SUMMARIZATION_FAILED)

    def test_get_error_type_timeout(self):
        """Test detection of timeout errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Processing timeout after 300 seconds'
        )
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_PROCESSING_TIMEOUT)

        entry.error_message = 'Request timed out waiting for response'
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_PROCESSING_TIMEOUT)

    def test_get_error_type_unknown(self):
        """Test detection of unknown errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Some random error occurred'
        )
        self.assertEqual(entry.get_error_type(), CaptureEntry.ERROR_TYPE_UNKNOWN)

    def test_get_error_type_empty_message(self):
        """Test error type with no error message."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message=''
        )
        self.assertIsNone(entry.get_error_type())


class CaptureEntryUserFriendlyErrorTests(TestCase):
    """Tests for user-friendly error message generation."""

    def setUp(self):
        self.user = create_test_user()

    def test_get_user_friendly_error_mic_denied(self):
        """Test user-friendly message for mic denied errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Microphone access denied'
        )
        error_info = entry.get_user_friendly_error()

        self.assertEqual(error_info['title'], 'Microphone Access Denied')
        self.assertIn('microphone', error_info['message'].lower())
        self.assertIn('browser settings', error_info['suggestion'].lower())
        self.assertFalse(error_info['can_retry'])

    def test_get_user_friendly_error_upload_failed(self):
        """Test user-friendly message for upload failures."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Upload to S3 failed'
        )
        error_info = entry.get_user_friendly_error()

        self.assertEqual(error_info['title'], 'Upload Failed')
        self.assertIn('internet connection', error_info['suggestion'].lower())
        self.assertTrue(error_info['can_retry'])

    def test_get_user_friendly_error_transcription_failed(self):
        """Test user-friendly message for transcription failures."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription service error'
        )
        error_info = entry.get_user_friendly_error()

        self.assertEqual(error_info['title'], 'Transcription Failed')
        self.assertIn('audio quality', error_info['suggestion'].lower())
        self.assertTrue(error_info['can_retry'])

    def test_get_user_friendly_error_timeout(self):
        """Test user-friendly message for timeout errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Processing timeout'
        )
        error_info = entry.get_user_friendly_error()

        self.assertEqual(error_info['title'], 'Processing Taking Longer Than Expected')
        self.assertIn('email', error_info['suggestion'].lower())
        self.assertFalse(error_info['can_retry'])


class CaptureEntryCanRetryTests(TestCase):
    """Tests for can_retry method."""

    def setUp(self):
        self.user = create_test_user()

    def test_can_retry_failed_retryable_error(self):
        """Test that failed entries with retryable errors can be retried."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription service temporarily unavailable'
        )
        self.assertTrue(entry.can_retry())

    def test_cannot_retry_non_failed_status(self):
        """Test that non-failed entries cannot be retried."""
        for status in [CaptureEntry.STATUS_READY, CaptureEntry.STATUS_TRANSCRIBING,
                       CaptureEntry.STATUS_SUMMARIZING, CaptureEntry.STATUS_UPLOADING]:
            entry = CaptureEntry.objects.create(
                user=self.user,
                status=status
            )
            self.assertFalse(entry.can_retry())

    def test_cannot_retry_mic_denied(self):
        """Test that mic denied errors cannot be retried."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Microphone access denied'
        )
        self.assertFalse(entry.can_retry())

    def test_cannot_retry_timeout(self):
        """Test that timeout errors cannot be retried (will email instead)."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Processing timeout after 300 seconds'
        )
        self.assertFalse(entry.can_retry())


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureRetryViewTests(TestCase):
    """Tests for CaptureRetryView."""

    def setUp(self):
        self.user = create_test_user(email='testuser@example.com')
        self.other_user = create_test_user(email='other@example.com')
        self.client = Client()
        self.client.login(email='testuser@example.com', password='testpass123')

        self.failed_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed: service error',
            audio_file_url='https://example.com/audio.mp3'
        )

    def test_retry_requires_login(self):
        """Test that retry endpoint requires authentication."""
        self.client.logout()
        url = reverse('capture:retry', kwargs={'pk': self.failed_entry.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    @patch('apps.capture.tasks.process_capture_entry')
    def test_retry_failed_entry_success(self, mock_process):
        """Test successful retry of a failed entry."""
        mock_process.return_value = {'success': True}
        url = reverse('capture:retry', kwargs={'pk': self.failed_entry.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('poll_url', data)

        # Verify status changed to transcribing
        self.failed_entry.refresh_from_db()
        self.assertEqual(self.failed_entry.status, CaptureEntry.STATUS_TRANSCRIBING)
        self.assertEqual(self.failed_entry.error_message, '')

    def test_retry_entry_not_found(self):
        """Test retry returns 404 for non-existent entry."""
        import uuid
        url = reverse('capture:retry', kwargs={'pk': uuid.uuid4()})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_retry_other_users_entry(self):
        """Test cannot retry another user's entry."""
        other_entry = CaptureEntry.objects.create(
            user=self.other_user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed'
        )
        url = reverse('capture:retry', kwargs={'pk': other_entry.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_retry_non_failed_entry(self):
        """Test cannot retry entry that is not failed."""
        ready_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_READY
        )
        url = reverse('capture:retry', kwargs={'pk': ready_entry.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Only failed entries', response.json()['error'])

    def test_retry_non_retryable_error(self):
        """Test cannot retry entry with non-retryable error."""
        non_retryable_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Microphone access denied'
        )
        url = reverse('capture:retry', kwargs={'pk': non_retryable_entry.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('cannot be retried', response.json()['error'])


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureDetailViewErrorDisplayTests(TestCase):
    """Tests for error display on detail page."""

    def setUp(self):
        self.user = create_test_user(email='testuser@example.com')
        self.client = Client()
        self.client.login(email='testuser@example.com', password='testpass123')

    def test_detail_page_shows_error_info_for_failed_entry(self):
        """Test that detail page shows error info for failed entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed: audio quality too low'
        )
        url = reverse('capture:detail', kwargs={'pk': entry.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('error_info', response.context)
        self.assertEqual(response.context['error_info']['title'], 'Transcription Failed')

    def test_detail_page_shows_retry_button_for_retryable_errors(self):
        """Test that detail page shows retry button for retryable errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed'
        )
        url = reverse('capture:detail', kwargs={'pk': entry.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'retry-btn')
        self.assertContains(response, 'Try Again')

    def test_detail_page_hides_retry_button_for_non_retryable_errors(self):
        """Test that detail page hides retry button for non-retryable errors."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Microphone access denied'
        )
        url = reverse('capture:detail', kwargs={'pk': entry.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The retry button should not be present
        self.assertNotContains(response, 'id="retry-btn"')

    def test_detail_page_no_error_info_for_ready_entry(self):
        """Test that ready entries don't have error_info in context."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_READY,
            summary='Test summary'
        )
        url = reverse('capture:detail', kwargs={'pk': entry.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('error_info', response.context)


class ProcessingCompleteEmailTests(TestCase):
    """Tests for processing complete email notification."""

    def setUp(self):
        self.user = create_test_user()

    def test_send_processing_complete_email_success(self):
        """Test successful sending of completion email."""
        from apps.capture.services.email import send_processing_complete_email

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_READY,
            summary='Test summary'
        )

        with patch.object(EmailMessage, 'send', return_value=1) as mock_send:
            result = send_processing_complete_email(entry)

        self.assertTrue(result['success'])
        mock_send.assert_called_once()

        # Verify completion_email_sent_at was set
        entry.refresh_from_db()
        self.assertIsNotNone(entry.completion_email_sent_at)

    def test_send_processing_complete_email_already_sent(self):
        """Test that email is not sent twice."""
        from apps.capture.services.email import send_processing_complete_email

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_READY,
            completion_email_sent_at=timezone.now()
        )

        result = send_processing_complete_email(entry)

        self.assertTrue(result['success'])
        self.assertTrue(result.get('already_sent'))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_processing_complete_email_failure(self):
        """Test handling of email send failure."""
        from apps.capture.services.email import send_processing_complete_email

        entry = CaptureEntry.objects.create(
            user=self.user,
            title='Test Recording',
            status=CaptureEntry.STATUS_READY
        )

        # Use a mock that raises on all method calls to the email instance
        with patch('apps.capture.services.email.EmailMessage') as MockEmail:
            mock_email_instance = MagicMock()
            mock_email_instance.send.side_effect = Exception('SMTP error')
            MockEmail.return_value = mock_email_instance

            result = send_processing_complete_email(entry)

        self.assertFalse(result['success'])
        self.assertIn('error', result)

        # Verify completion_email_sent_at was NOT set
        entry.refresh_from_db()
        self.assertIsNone(entry.completion_email_sent_at)


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class CaptureStatusViewErrorTests(TestCase):
    """Tests for error info in status API responses."""

    def setUp(self):
        self.user = create_test_user(email='testuser@example.com')
        self.client = Client()
        self.client.login(email='testuser@example.com', password='testpass123')

    def test_status_view_returns_error_message_for_failed(self):
        """Test that status view returns error message for failed entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_FAILED,
            error_message='Transcription failed: audio quality too low'
        )
        url = reverse('capture:status', kwargs={'entry_id': entry.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['error_message'], 'Transcription failed: audio quality too low')
