"""
Transcription service using OpenAI Whisper API.

This service handles audio transcription for the Capture feature, including:
- Downloading audio from S3 URLs
- Handling Whisper's 25MB file size limit with compression
- Transcribing audio using OpenAI's Whisper API
- Updating CaptureEntry status and transcript fields

Usage:
    from apps.capture.services import transcription_service

    # Transcribe audio and update the CaptureEntry
    result = transcription_service.transcribe_audio(capture_entry)

    if result['success']:
        print(f"Transcript: {result['transcript']}")
    else:
        print(f"Error: {result['error']}")
"""

import io
import logging
import tempfile
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Whisper API limits
WHISPER_MAX_FILE_SIZE_MB = 25
WHISPER_MAX_FILE_SIZE_BYTES = WHISPER_MAX_FILE_SIZE_MB * 1024 * 1024

# Supported audio formats for Whisper
SUPPORTED_FORMATS = ['flac', 'm4a', 'mp3', 'mp4', 'mpeg', 'mpga', 'oga', 'ogg', 'wav', 'webm']


class TranscriptionError(Exception):
    """Custom exception for transcription errors."""

    def __init__(self, message: str, user_message: str = None):
        super().__init__(message)
        self.user_message = user_message or message


class TranscriptionService:
    """Service for transcribing audio using OpenAI Whisper API."""

    def __init__(self):
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client if API key is available."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI package not installed. Run: pip install openai")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

    @property
    def is_available(self) -> bool:
        """Check if transcription service is available."""
        return self.client is not None

    def transcribe_audio(self, capture_entry) -> dict:
        """
        Transcribe audio from a CaptureEntry and update its fields.

        Args:
            capture_entry: CaptureEntry model instance with audio_file_url

        Returns:
            dict with keys:
                - success (bool): Whether transcription succeeded
                - transcript (str): The transcript text (if successful)
                - error (str): Error message (if failed)
        """
        from apps.capture.models import CaptureEntry

        if not self.is_available:
            error_msg = "Transcription service not available - OpenAI API key not configured"
            logger.warning(error_msg)
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = "Transcription service is temporarily unavailable. Please try again later."
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': error_msg}

        if not capture_entry.audio_file_url:
            error_msg = "No audio file URL provided"
            logger.error(f"CaptureEntry {capture_entry.id}: {error_msg}")
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = "No audio file found. Please upload your recording again."
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': error_msg}

        try:
            # Download audio file
            logger.info(f"CaptureEntry {capture_entry.id}: Downloading audio from S3")
            audio_data, filename = self._download_audio(capture_entry.audio_file_url)

            # Check file size and compress if needed
            file_size = len(audio_data)
            if file_size > WHISPER_MAX_FILE_SIZE_BYTES:
                logger.info(
                    f"CaptureEntry {capture_entry.id}: Audio file is {file_size / 1024 / 1024:.1f}MB, "
                    f"compressing to meet {WHISPER_MAX_FILE_SIZE_MB}MB limit"
                )
                audio_data, filename = self._compress_audio(audio_data, filename)

            # Transcribe with Whisper
            logger.info(f"CaptureEntry {capture_entry.id}: Sending to Whisper API")
            transcript = self._call_whisper_api(audio_data, filename)

            # Update CaptureEntry on success
            capture_entry.transcript = transcript
            capture_entry.status = CaptureEntry.STATUS_SUMMARIZING
            capture_entry.error_message = ''
            capture_entry.save(update_fields=['transcript', 'status', 'error_message'])

            logger.info(f"CaptureEntry {capture_entry.id}: Transcription complete, {len(transcript)} characters")
            return {'success': True, 'transcript': transcript}

        except TranscriptionError as e:
            logger.error(f"CaptureEntry {capture_entry.id}: Transcription error - {e}")
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = e.user_message
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': str(e)}

        except Exception as e:
            logger.exception(f"CaptureEntry {capture_entry.id}: Unexpected error during transcription")
            capture_entry.status = CaptureEntry.STATUS_FAILED
            capture_entry.error_message = "An unexpected error occurred during transcription. Please try again."
            capture_entry.save(update_fields=['status', 'error_message'])
            return {'success': False, 'error': str(e)}

    def _download_audio(self, audio_url: str) -> tuple[bytes, str]:
        """
        Download audio file from URL.

        Args:
            audio_url: URL to download audio from (typically S3 presigned URL)

        Returns:
            Tuple of (audio_bytes, filename)

        Raises:
            TranscriptionError: If download fails
        """
        try:
            response = requests.get(audio_url, timeout=120)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise TranscriptionError(
                "Audio download timed out",
                "The audio file took too long to download. Please try again."
            )
        except requests.exceptions.RequestException as e:
            raise TranscriptionError(
                f"Failed to download audio: {e}",
                "Unable to access your audio file. The link may have expired - please upload again."
            )

        # Determine filename from URL or content-type
        content_type = response.headers.get('content-type', '')
        filename = self._get_filename_from_content_type(content_type, audio_url)

        return response.content, filename

    def _get_filename_from_content_type(self, content_type: str, url: str) -> str:
        """Determine appropriate filename based on content type or URL."""
        # Map content types to extensions
        content_type_map = {
            'audio/mpeg': 'audio.mp3',
            'audio/mp3': 'audio.mp3',
            'audio/mp4': 'audio.m4a',
            'audio/m4a': 'audio.m4a',
            'audio/wav': 'audio.wav',
            'audio/wave': 'audio.wav',
            'audio/x-wav': 'audio.wav',
            'audio/webm': 'audio.webm',
            'audio/ogg': 'audio.ogg',
            'audio/flac': 'audio.flac',
            'audio/x-flac': 'audio.flac',
        }

        # Try content type first
        for ct, filename in content_type_map.items():
            if ct in content_type.lower():
                return filename

        # Try to get extension from URL
        url_lower = url.lower()
        for ext in SUPPORTED_FORMATS:
            if f'.{ext}' in url_lower:
                return f'audio.{ext}'

        # Default to mp3 (most common format)
        return 'audio.mp3'

    def _compress_audio(self, audio_data: bytes, filename: str) -> tuple[bytes, str]:
        """
        Compress audio to meet Whisper's 25MB limit.

        Uses ffmpeg to convert to compressed mp3 format with reduced bitrate.

        Args:
            audio_data: Original audio bytes
            filename: Original filename

        Returns:
            Tuple of (compressed_audio_bytes, new_filename)

        Raises:
            TranscriptionError: If compression fails or ffmpeg not available
        """
        try:
            import subprocess

            # Check if ffmpeg is available
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise TranscriptionError(
                    "ffmpeg not available for audio compression",
                    "Your audio file is too large. Please record a shorter message (under 30 minutes)."
                )

            # Write original audio to temp file
            with tempfile.NamedTemporaryFile(suffix=f'.{filename.split(".")[-1]}', delete=False) as input_file:
                input_file.write(audio_data)
                input_path = input_file.name

            # Create output temp file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as output_file:
                output_path = output_file.name

            try:
                # Calculate target bitrate to get under 25MB
                # Formula: bitrate (kbps) = (target_size_mb * 8 * 1024) / duration_seconds
                # We'll use 64kbps as a reasonable minimum for speech
                target_bitrate = '64k'

                # Run ffmpeg compression
                result = subprocess.run(
                    [
                        'ffmpeg', '-y',
                        '-i', input_path,
                        '-vn',  # No video
                        '-ar', '16000',  # 16kHz sample rate (good for speech)
                        '-ac', '1',  # Mono
                        '-b:a', target_bitrate,  # Target bitrate
                        '-f', 'mp3',
                        output_path
                    ],
                    capture_output=True,
                    timeout=300  # 5 minute timeout for compression
                )

                if result.returncode != 0:
                    logger.error(f"ffmpeg compression failed: {result.stderr.decode()}")
                    raise TranscriptionError(
                        f"Audio compression failed: {result.stderr.decode()[:200]}",
                        "Unable to process your audio file. Please try a different format (mp3 or m4a recommended)."
                    )

                # Read compressed audio
                with open(output_path, 'rb') as f:
                    compressed_data = f.read()

                # Verify size is under limit
                if len(compressed_data) > WHISPER_MAX_FILE_SIZE_BYTES:
                    raise TranscriptionError(
                        f"Compressed audio still too large: {len(compressed_data) / 1024 / 1024:.1f}MB",
                        "Your audio file is too long to process. Please record a shorter message (under 2 hours)."
                    )

                logger.info(
                    f"Compressed audio from {len(audio_data) / 1024 / 1024:.1f}MB "
                    f"to {len(compressed_data) / 1024 / 1024:.1f}MB"
                )

                return compressed_data, 'audio.mp3'

            finally:
                # Clean up temp files
                import os
                try:
                    os.unlink(input_path)
                except OSError:
                    pass
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

        except TranscriptionError:
            raise
        except Exception as e:
            logger.exception("Unexpected error during audio compression")
            raise TranscriptionError(
                f"Audio compression failed: {e}",
                "Unable to process your audio file. Please try recording again."
            )

    def _call_whisper_api(self, audio_data: bytes, filename: str) -> str:
        """
        Call OpenAI Whisper API to transcribe audio.

        Args:
            audio_data: Audio file bytes
            filename: Filename with appropriate extension

        Returns:
            Transcript text

        Raises:
            TranscriptionError: If API call fails
        """
        try:
            # Create a file-like object for the API
            audio_file = io.BytesIO(audio_data)
            audio_file.name = filename

            response = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

            # The response is the transcript text directly when response_format="text"
            transcript = response.strip() if isinstance(response, str) else str(response).strip()

            if not transcript:
                raise TranscriptionError(
                    "Whisper returned empty transcript",
                    "No speech was detected in your recording. Please try again with clearer audio."
                )

            return transcript

        except TranscriptionError:
            raise
        except Exception as e:
            error_str = str(e).lower()

            # Handle specific OpenAI API errors
            if 'invalid_api_key' in error_str or 'authentication' in error_str:
                raise TranscriptionError(
                    f"OpenAI API authentication failed: {e}",
                    "Transcription service is temporarily unavailable. Please try again later."
                )
            elif 'rate_limit' in error_str:
                raise TranscriptionError(
                    f"OpenAI API rate limit exceeded: {e}",
                    "The transcription service is busy. Please wait a few minutes and try again."
                )
            elif 'invalid_file' in error_str or 'unsupported' in error_str:
                raise TranscriptionError(
                    f"Invalid audio file format: {e}",
                    "Your audio format is not supported. Please use mp3, m4a, wav, or webm."
                )
            else:
                raise TranscriptionError(
                    f"Whisper API error: {e}",
                    "Transcription failed. Please try again or contact support if the problem persists."
                )


# Singleton instance
transcription_service = TranscriptionService()
