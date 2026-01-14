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
