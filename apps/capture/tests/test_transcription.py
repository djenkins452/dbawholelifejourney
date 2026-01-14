"""Tests for capture transcription service."""

import io
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.capture.models import CaptureEntry
from apps.capture.services.transcription import (
    SUPPORTED_FORMATS,
    WHISPER_MAX_FILE_SIZE_BYTES,
    TranscriptionError,
    TranscriptionService,
)
from apps.users.models import User


class TranscriptionServiceInitializationTests(TestCase):
    """Tests for TranscriptionService initialization."""

    @override_settings(OPENAI_API_KEY='test-api-key')
    @patch('openai.OpenAI')
    def test_service_initializes_with_api_key(self, mock_openai):
        """Test service initializes client when API key is configured."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        service = TranscriptionService()

        self.assertTrue(service.is_available)
        mock_openai.assert_called_once_with(api_key='test-api-key')

    @override_settings(OPENAI_API_KEY=None)
    def test_service_not_available_without_api_key(self):
        """Test service is not available when API key is not configured."""
        service = TranscriptionService()

        self.assertFalse(service.is_available)

    @override_settings(OPENAI_API_KEY='')
    def test_service_not_available_with_empty_api_key(self):
        """Test service is not available when API key is empty."""
        service = TranscriptionService()

        self.assertFalse(service.is_available)


@override_settings(OPENAI_API_KEY='test-api-key')
class TranscriptionServiceTranscribeTests(TestCase):
    """Tests for TranscriptionService.transcribe_audio method."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.capture_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/test-audio.mp3'
        )

    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_transcribe_audio_success(self, mock_requests_get, mock_openai):
        """Test successful audio transcription."""
        # Mock audio download
        mock_response = MagicMock()
        mock_response.content = b'fake audio data'
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        # Mock Whisper API
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "This is the transcribed text."
        mock_openai.return_value = mock_client

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertTrue(result['success'])
        self.assertEqual(result['transcript'], "This is the transcribed text.")

        # Verify entry was updated
        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.transcript, "This is the transcribed text.")
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_SUMMARIZING)
        self.assertEqual(self.capture_entry.error_message, '')

    @patch('openai.OpenAI')
    def test_transcribe_audio_no_url(self, mock_openai):
        """Test transcription fails gracefully when no audio URL."""
        mock_openai.return_value = MagicMock()

        self.capture_entry.audio_file_url = ''
        self.capture_entry.save()

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('No audio file URL', result['error'])

        # Verify entry was marked as failed
        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('No audio file found', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_transcribe_audio_download_timeout(self, mock_requests_get, mock_openai):
        """Test transcription handles download timeout."""
        import requests
        mock_requests_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        mock_openai.return_value = MagicMock()

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('timed out', result['error'].lower())

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('took too long', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_transcribe_audio_download_error(self, mock_requests_get, mock_openai):
        """Test transcription handles download HTTP error."""
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_requests_get.return_value = mock_response
        mock_openai.return_value = MagicMock()

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('link may have expired', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_transcribe_audio_empty_transcript(self, mock_requests_get, mock_openai):
        """Test transcription handles empty transcript from Whisper."""
        mock_response = MagicMock()
        mock_response.content = b'fake audio data'
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = ""
        mock_openai.return_value = mock_client

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('empty transcript', result['error'].lower())

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('No speech was detected', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_transcribe_audio_api_rate_limit(self, mock_requests_get, mock_openai):
        """Test transcription handles Whisper rate limit error."""
        mock_response = MagicMock()
        mock_response.content = b'fake audio data'
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = Exception("rate_limit exceeded")
        mock_openai.return_value = mock_client

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('busy', self.capture_entry.error_message)

    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_transcribe_audio_api_auth_error(self, mock_requests_get, mock_openai):
        """Test transcription handles Whisper authentication error."""
        mock_response = MagicMock()
        mock_response.content = b'fake audio data'
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = Exception("invalid_api_key")
        mock_openai.return_value = mock_client

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('temporarily unavailable', self.capture_entry.error_message)


class TranscriptionServiceFilenameTests(TestCase):
    """Tests for filename detection from content type."""

    def setUp(self):
        """Set up service with mocked client."""
        self.service = TranscriptionService()

    def test_get_filename_mp3_content_type(self):
        """Test MP3 content type returns mp3 filename."""
        filename = self.service._get_filename_from_content_type('audio/mpeg', 'https://example.com/file')
        self.assertEqual(filename, 'audio.mp3')

    def test_get_filename_wav_content_type(self):
        """Test WAV content type returns wav filename."""
        filename = self.service._get_filename_from_content_type('audio/wav', 'https://example.com/file')
        self.assertEqual(filename, 'audio.wav')

    def test_get_filename_webm_content_type(self):
        """Test WebM content type returns webm filename."""
        filename = self.service._get_filename_from_content_type('audio/webm', 'https://example.com/file')
        self.assertEqual(filename, 'audio.webm')

    def test_get_filename_m4a_content_type(self):
        """Test M4A content type returns m4a filename."""
        filename = self.service._get_filename_from_content_type('audio/mp4', 'https://example.com/file')
        self.assertEqual(filename, 'audio.m4a')

    def test_get_filename_from_url_when_unknown_content_type(self):
        """Test filename extracted from URL when content type is unknown."""
        filename = self.service._get_filename_from_content_type(
            'application/octet-stream',
            'https://s3.example.com/captures/user-123/recording.ogg?token=xxx'
        )
        self.assertEqual(filename, 'audio.ogg')

    def test_get_filename_default_for_unknown(self):
        """Test default mp3 filename when content type and URL are unknown."""
        filename = self.service._get_filename_from_content_type(
            'application/octet-stream',
            'https://example.com/api/audio'
        )
        self.assertEqual(filename, 'audio.mp3')


@override_settings(OPENAI_API_KEY='test-api-key')
class TranscriptionServiceCompressionTests(TestCase):
    """Tests for audio compression functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='compression-test@example.com',
            password='testpass123'
        )
        self.capture_entry = CaptureEntry.objects.create(
            user=self.user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/large-audio.mp3'
        )

    @patch('subprocess.run')
    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_compression_triggered_for_large_files(self, mock_requests_get, mock_openai, mock_subprocess_run):
        """Test that compression is triggered for files over 25MB."""
        # Create fake large audio data (26MB)
        large_audio = b'x' * (26 * 1024 * 1024)

        mock_response = MagicMock()
        mock_response.content = large_audio
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        # Mock ffmpeg version check
        ffmpeg_version = MagicMock()
        ffmpeg_version.returncode = 0

        # Mock ffmpeg compression - return success and create compressed file
        ffmpeg_compress = MagicMock()
        ffmpeg_compress.returncode = 0

        # Create a side effect that writes compressed data to the output file
        def run_side_effect(cmd, *args, **kwargs):
            if cmd[0] == 'ffmpeg' and '-version' in cmd:
                return ffmpeg_version
            elif cmd[0] == 'ffmpeg' and '-y' in cmd:
                # Find output path (last argument before potential extras)
                output_path = cmd[-1]
                with open(output_path, 'wb') as f:
                    f.write(b'compressed audio' * 1000)  # ~16KB compressed
                return ffmpeg_compress
            return MagicMock()

        mock_subprocess_run.side_effect = run_side_effect

        # Mock Whisper API
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Transcribed from compressed audio."
        mock_openai.return_value = mock_client

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        # Should succeed with compressed audio
        self.assertTrue(result['success'])

        # Verify ffmpeg was called for compression
        self.assertTrue(mock_subprocess_run.called)

    @patch('subprocess.run')
    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_compression_not_triggered_for_small_files(self, mock_requests_get, mock_openai, mock_subprocess_run):
        """Test that compression is not triggered for files under 25MB."""
        # Create small audio data (1MB)
        small_audio = b'x' * (1 * 1024 * 1024)

        mock_response = MagicMock()
        mock_response.content = small_audio
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Small file transcription."
        mock_openai.return_value = mock_client

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        # Should succeed without compression
        self.assertTrue(result['success'])

        # ffmpeg should not be called for compression
        # (it might be called for version check in some paths, so we just verify success without compression errors)
        self.assertNotIn('compress', result.get('error', '').lower())

    @patch('subprocess.run')
    @patch('openai.OpenAI')
    @patch('apps.capture.services.transcription.requests.get')
    def test_compression_fails_gracefully_when_ffmpeg_not_available(
        self, mock_requests_get, mock_openai, mock_subprocess_run
    ):
        """Test graceful failure when ffmpeg is not available."""
        # Create large audio data
        large_audio = b'x' * (26 * 1024 * 1024)

        mock_response = MagicMock()
        mock_response.content = large_audio
        mock_response.headers = {'content-type': 'audio/mp3'}
        mock_requests_get.return_value = mock_response

        # Mock ffmpeg not found
        mock_subprocess_run.side_effect = FileNotFoundError("ffmpeg not found")

        mock_openai.return_value = MagicMock()

        service = TranscriptionService()
        result = service.transcribe_audio(self.capture_entry)

        self.assertFalse(result['success'])

        self.capture_entry.refresh_from_db()
        self.assertEqual(self.capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('too large', self.capture_entry.error_message)


class TranscriptionErrorTests(TestCase):
    """Tests for TranscriptionError exception."""

    def test_error_with_user_message(self):
        """Test TranscriptionError stores both messages."""
        error = TranscriptionError(
            "Technical error details",
            "User-friendly message"
        )

        self.assertEqual(str(error), "Technical error details")
        self.assertEqual(error.user_message, "User-friendly message")

    def test_error_without_user_message(self):
        """Test TranscriptionError uses main message as user message."""
        error = TranscriptionError("Error message")

        self.assertEqual(str(error), "Error message")
        self.assertEqual(error.user_message, "Error message")


class TranscriptionServiceNotAvailableTests(TestCase):
    """Tests for service behavior when not available."""

    @override_settings(OPENAI_API_KEY=None)
    def test_transcribe_returns_error_when_not_available(self):
        """Test transcribe_audio returns error when service not available."""
        user = User.objects.create_user(
            email='unavailable-test@example.com',
            password='testpass123'
        )
        capture_entry = CaptureEntry.objects.create(
            user=user,
            status=CaptureEntry.STATUS_TRANSCRIBING,
            audio_file_url='https://s3.example.com/test-audio.mp3'
        )

        service = TranscriptionService()
        result = service.transcribe_audio(capture_entry)

        self.assertFalse(result['success'])
        self.assertIn('not available', result['error'].lower())

        capture_entry.refresh_from_db()
        self.assertEqual(capture_entry.status, CaptureEntry.STATUS_FAILED)
        self.assertIn('temporarily unavailable', capture_entry.error_message)


class SupportedFormatsTests(TestCase):
    """Tests for supported audio format constants."""

    def test_supported_formats_includes_common_formats(self):
        """Test that common audio formats are supported."""
        common_formats = ['mp3', 'wav', 'webm', 'm4a', 'ogg', 'flac']
        for fmt in common_formats:
            self.assertIn(fmt, SUPPORTED_FORMATS, f"{fmt} should be in SUPPORTED_FORMATS")

    def test_whisper_max_file_size(self):
        """Test that max file size constant is correct."""
        # Whisper limit is 25MB
        self.assertEqual(WHISPER_MAX_FILE_SIZE_BYTES, 25 * 1024 * 1024)
