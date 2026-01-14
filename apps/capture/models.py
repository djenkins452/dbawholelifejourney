"""Capture models - Audio recordings, transcripts, and summaries."""

import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class CaptureEntry(TimeStampedModel):
    """
    Model for storing audio recordings, transcripts, and AI-generated summaries.

    Workflow:
    1. User uploads audio -> status='uploading'
    2. Audio uploaded to S3 -> status='transcribing'
    3. Whisper transcription complete -> status='summarizing'
    4. AI summary generated -> status='ready'
    5. Any error -> status='failed' with error_message

    Audio files are stored in S3 with signed URLs that expire after 7 days.
    """

    # Status choices for processing pipeline
    STATUS_UPLOADING = 'uploading'
    STATUS_TRANSCRIBING = 'transcribing'
    STATUS_SUMMARIZING = 'summarizing'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_UPLOADING, 'Uploading'),
        (STATUS_TRANSCRIBING, 'Transcribing'),
        (STATUS_SUMMARIZING, 'Summarizing'),
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
    ]

    # Category choices
    CATEGORY_FAITH = 'faith'
    CATEGORY_ORGANIZE = 'organize'

    CATEGORY_CHOICES = [
        (CATEGORY_FAITH, 'Faith'),
        (CATEGORY_ORGANIZE, 'Organize'),
    ]

    # Subcategory choices
    SUBCATEGORY_SERMON = 'sermon'
    SUBCATEGORY_BIBLE_STUDY = 'bible_study'
    SUBCATEGORY_DEVOTIONAL = 'devotional'
    SUBCATEGORY_MEETING = 'meeting'
    SUBCATEGORY_NOTES = 'notes'
    SUBCATEGORY_PERSONAL = 'personal'

    SUBCATEGORY_CHOICES = [
        (SUBCATEGORY_SERMON, 'Sermon'),
        (SUBCATEGORY_BIBLE_STUDY, 'Bible Study'),
        (SUBCATEGORY_DEVOTIONAL, 'Devotional'),
        (SUBCATEGORY_MEETING, 'Meeting'),
        (SUBCATEGORY_NOTES, 'Notes'),
        (SUBCATEGORY_PERSONAL, 'Personal'),
    ]

    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this capture entry"
    )

    # User relationship
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='capture_entries',
        help_text="User who created this capture"
    )

    # Basic info
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Title for this capture (can be auto-generated from summary)"
    )

    # Audio file info
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration of the audio recording in seconds"
    )

    audio_file_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="S3 signed URL for the audio file"
    )

    audio_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the S3 signed URL expires"
    )

    # Content
    transcript = models.TextField(
        blank=True,
        help_text="Full transcript from Whisper"
    )

    summary = models.TextField(
        blank=True,
        help_text="AI-generated BLUF summary"
    )

    # Classification
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        blank=True,
        help_text="Primary category for this capture"
    )

    subcategory = models.CharField(
        max_length=20,
        choices=SUBCATEGORY_CHOICES,
        blank=True,
        help_text="Subcategory for this capture"
    )

    # Processing status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADING,
        db_index=True,
        help_text="Current processing status"
    )

    error_message = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )

    # Reminder tracking
    reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the audio expiration reminder email was sent"
    )

    # Processing completion notification
    completion_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the delayed processing completion email was sent"
    )

    # Error type constants for user-friendly messages
    ERROR_TYPE_MIC_DENIED = 'mic_denied'
    ERROR_TYPE_UPLOAD_FAILED = 'upload_failed'
    ERROR_TYPE_TRANSCRIPTION_FAILED = 'transcription_failed'
    ERROR_TYPE_SUMMARIZATION_FAILED = 'summarization_failed'
    ERROR_TYPE_PROCESSING_TIMEOUT = 'processing_timeout'
    ERROR_TYPE_UNKNOWN = 'unknown'

    def get_error_type(self):
        """
        Determine the error type from the error message for UI display.

        Returns one of the ERROR_TYPE_* constants based on error message content.
        """
        if not self.error_message:
            return None

        error_lower = self.error_message.lower()

        if 'microphone' in error_lower or 'mic' in error_lower or 'permission denied' in error_lower:
            return self.ERROR_TYPE_MIC_DENIED
        elif 'upload' in error_lower or 's3' in error_lower or 'storage' in error_lower:
            return self.ERROR_TYPE_UPLOAD_FAILED
        elif 'transcri' in error_lower or 'whisper' in error_lower or 'speech' in error_lower:
            return self.ERROR_TYPE_TRANSCRIPTION_FAILED
        elif 'summar' in error_lower or 'openai' in error_lower:
            return self.ERROR_TYPE_SUMMARIZATION_FAILED
        elif 'timeout' in error_lower or 'timed out' in error_lower:
            return self.ERROR_TYPE_PROCESSING_TIMEOUT
        else:
            return self.ERROR_TYPE_UNKNOWN

    def get_user_friendly_error(self):
        """
        Get a user-friendly error message with helpful suggestions.

        Returns a dict with 'title', 'message', and 'suggestion' keys.
        """
        error_type = self.get_error_type()

        error_messages = {
            self.ERROR_TYPE_MIC_DENIED: {
                'title': 'Microphone Access Denied',
                'message': 'We could not access your microphone.',
                'suggestion': 'Please allow microphone access in your browser settings and try recording again.',
                'can_retry': False,
            },
            self.ERROR_TYPE_UPLOAD_FAILED: {
                'title': 'Upload Failed',
                'message': 'We could not upload your audio file.',
                'suggestion': 'Please check your internet connection and try again.',
                'can_retry': True,
            },
            self.ERROR_TYPE_TRANSCRIPTION_FAILED: {
                'title': 'Transcription Failed',
                'message': 'We could not transcribe your audio.',
                'suggestion': 'Audio quality may be too low. Try uploading a clearer recording with less background noise.',
                'can_retry': True,
            },
            self.ERROR_TYPE_SUMMARIZATION_FAILED: {
                'title': 'Summary Generation Failed',
                'message': 'We could not generate a summary.',
                'suggestion': 'Please try again. If the problem persists, the transcript is still available.',
                'can_retry': True,
            },
            self.ERROR_TYPE_PROCESSING_TIMEOUT: {
                'title': 'Processing Taking Longer Than Expected',
                'message': 'Your recording is still being processed.',
                'suggestion': 'We will email you when your recording is ready. You can also check back later.',
                'can_retry': False,
            },
            self.ERROR_TYPE_UNKNOWN: {
                'title': 'Processing Failed',
                'message': self.error_message or 'An unexpected error occurred.',
                'suggestion': 'Please try again. If the problem persists, contact support.',
                'can_retry': True,
            },
        }

        return error_messages.get(error_type, error_messages[self.ERROR_TYPE_UNKNOWN])

    def can_retry(self):
        """Check if this entry can be retried."""
        if self.status != self.STATUS_FAILED:
            return False
        error_info = self.get_user_friendly_error()
        return error_info.get('can_retry', False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Capture Entry'
        verbose_name_plural = 'Capture Entries'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['category', '-created_at']),
        ]

    def __str__(self):
        if self.title:
            return f"{self.title} ({self.get_status_display()})"
        return f"Capture {self.id} ({self.get_status_display()})"
