"""Capture models - Audio recordings, transcripts, and summaries."""

import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class MultimodalArtifact(TimeStampedModel):
    """A user-uploaded artifact (image/PDF/scan/receipt/screenshot) that OpenAI PERCEIVES.

    WLJ stores it ONLY for provenance + deduplication + audit — it never interprets pixels.
    The model extracts candidate facts/actions and references this by id; the resolved
    deterministic record (e.g. a WeightEntry) links back, so every image-derived fact is
    traceable to its source (WLJ stays the system of record). This is the ONE new storage
    seam for Multimodal Truth; the candidate → validate → confirm → execute → audit spine
    is entirely reused.
    """

    STATUS_CHOICES = [
        ('received', 'Received'),
        ('resolved', 'Resolved'),      # produced a deterministic record
        ('duplicate', 'Duplicate'),    # same content hash already seen
        ('rejected', 'Rejected'),      # failed validation / user declined
    ]

    # Durable-storage lifecycle (distinct from `status`, which is the truth-
    # resolution lifecycle). Original bytes are persisted to durable object
    # storage by a BACKGROUND worker so the request path never blocks on I/O
    # (docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §3–§4). Retrieval must handle
    # `pending` gracefully — eventual consistency, not failure.
    STORAGE_PENDING = 'pending'    # queued for durable storage, not yet written
    STORAGE_STORED = 'stored'      # original durably persisted (storage_ref set)
    STORAGE_FAILED = 'failed'      # durable write failed (retryable)
    STORAGE_SKIPPED = 'skipped'    # no bytes to store (e.g. hash-only record)
    STORAGE_STATUS_CHOICES = [
        (STORAGE_PENDING, 'Pending'),
        (STORAGE_STORED, 'Stored'),
        (STORAGE_FAILED, 'Failed'),
        (STORAGE_SKIPPED, 'Skipped'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='multimodal_artifacts',
    )
    sha256 = models.CharField(
        max_length=64, db_index=True,
        help_text="Content hash — artifact-level dedup + integrity. WLJ hashes; never parses.",
    )
    content_type = models.CharField(max_length=100)          # image/jpeg, application/pdf, …
    original_filename = models.CharField(
        max_length=255, blank=True,
        help_text="Filename the user uploaded (identity + retrieval; may be blank for chat images).",
    )
    storage_ref = models.CharField(max_length=500, blank=True)  # durable object-storage name/path
    storage_status = models.CharField(
        max_length=20, choices=STORAGE_STATUS_CHOICES, default=STORAGE_PENDING,
        db_index=True,
        help_text="Durable-storage lifecycle. Written by the background persist task.",
    )
    byte_size = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Original size in bytes (metadata + integrity check).",
    )
    kind = models.CharField(
        max_length=50, blank=True,
        help_text="Model-declared kind (scale_photo, dexcom, receipt, …) — a label, not truth.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')

    # Perception lifecycle (Phase 1.3). DETERMINISTIC decode only — WLJ extracts
    # the text/transcript literally present in the artifact (pdfplumber, later
    # Whisper, …); it NEVER interprets. The conversational model does all
    # perception/reasoning over `extracted_text`.
    PERCEPTION_PENDING = 'pending'        # queued for extraction
    PERCEPTION_DONE = 'done'              # extracted_text populated
    PERCEPTION_FAILED = 'failed'          # extraction errored (retryable)
    PERCEPTION_UNSUPPORTED = 'unsupported'  # no extractor for this type yet
    PERCEPTION_NONE = 'none'              # not applicable (e.g. images — model sees directly)
    PERCEPTION_STATUS_CHOICES = [
        (PERCEPTION_PENDING, 'Pending'),
        (PERCEPTION_DONE, 'Done'),
        (PERCEPTION_FAILED, 'Failed'),
        (PERCEPTION_UNSUPPORTED, 'Unsupported'),
        (PERCEPTION_NONE, 'None'),
    ]
    perception_status = models.CharField(
        max_length=20, choices=PERCEPTION_STATUS_CHOICES, default=PERCEPTION_NONE,
        db_index=True,
        help_text="Deterministic-extraction lifecycle. Written by the background perceive task.",
    )
    extracted_text = models.TextField(
        blank=True,
        help_text="Deterministically extracted text/transcript (pdfplumber, Whisper, …). "
                  "Literal decode — never an interpretation. The model reasons over this.",
    )
    page_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="Pages/segments/frames (metadata).",
    )
    frames = models.JSONField(
        default=list, blank=True,
        help_text="Video only: sampled representative frames [{t: seconds, b64: jpeg}] "
                  "delivered to the model's image-perception path. Deterministic decode.",
    )

    # Conversation linkage (provenance + multi-turn retrieval): the conversation
    # this artifact was FIRST uploaded/referenced in. Soft id (matches the
    # resolved_object_id pattern — no cross-app FK cycle). Lets the CoS surface
    # "what you uploaded earlier in THIS conversation" and answer follow-ups
    # without re-attaching.
    source_conversation_id = models.IntegerField(null=True, blank=True, db_index=True)

    # Provenance: the deterministic record this artifact produced.
    resolved_intent = models.CharField(max_length=80, blank=True)
    resolved_object_type = models.CharField(max_length=80, blank=True)
    resolved_object_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'sha256'], name='uniq_user_artifact_hash',
            ),
        ]
        verbose_name = "Multimodal Artifact"

    def __str__(self):
        return f"{self.content_type} ({self.sha256[:10]}) — {self.status}"

    @property
    def is_durably_stored(self):
        """True once the original has been persisted to durable storage."""
        return self.storage_status == self.STORAGE_STORED and bool(self.storage_ref)

    @property
    def has_perception(self):
        """True once deterministic text/transcript has been extracted."""
        return self.perception_status == self.PERCEPTION_DONE and bool(self.extracted_text)

    @property
    def perception_pending(self):
        """True while extraction is queued/in-flight (eventual consistency)."""
        return self.perception_status == self.PERCEPTION_PENDING

    @property
    def storage_pending(self):
        """True while durable persistence is queued/in-flight (eventual consistency)."""
        return self.storage_status == self.STORAGE_PENDING


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

    # Link to pending capture for tracking
    pending_client_id = models.CharField(
        max_length=36,
        blank=True,
        help_text="Links to PendingCapture.client_id for upload tracking"
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


class PendingCapture(TimeStampedModel):
    """
    Tracks pending recordings that exist in client IndexedDB.

    This model enables cross-device awareness - if a user has a pending recording
    on their phone, they'll see a reminder on their laptop. It also tracks upload
    attempts and errors for resilient upload handling.

    Workflow:
    1. Recording starts/completes on client -> client registers PendingCapture
    2. Client attempts upload with retries
    3. On success -> status='completed', linked to CaptureEntry
    4. On abandon -> status='abandoned'
    """

    # Status choices
    STATUS_PENDING = 'pending'
    STATUS_UPLOADING = 'uploading'
    STATUS_UPLOADED = 'uploaded'
    STATUS_DOWNLOADED = 'downloaded'
    STATUS_COMPLETED = 'completed'
    STATUS_ABANDONED = 'abandoned'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Upload'),
        (STATUS_UPLOADING, 'Uploading'),
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_DOWNLOADED, 'Downloaded'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_ABANDONED, 'Abandoned'),
    ]

    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this pending capture"
    )

    # User relationship
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pending_captures',
        help_text="User who created this pending capture"
    )

    # Client-side tracking
    client_id = models.CharField(
        max_length=36,
        help_text="UUID generated by client browser for this recording"
    )

    device_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Device/browser identifier for cross-device awareness"
    )

    # Recording metadata
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration of the recording in seconds"
    )

    file_size_bytes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Size of the audio file in bytes"
    )

    mime_type = models.CharField(
        max_length=50,
        default='audio/webm',
        help_text="MIME type of the audio file"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Current status of this pending capture"
    )

    # Upload tracking
    upload_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of upload attempts made"
    )

    last_upload_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last upload attempt was made"
    )

    last_error = models.TextField(
        blank=True,
        help_text="Error message from last failed attempt"
    )

    # Linked CaptureEntry (once upload succeeds)
    capture_entry = models.OneToOneField(
        'CaptureEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pending_capture',
        help_text="The CaptureEntry created when upload succeeded"
    )

    # Activity tracking
    last_heartbeat_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Last time client pinged (for stale detection)"
    )

    last_reminder_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the last reminder notification was sent"
    )

    # Partial recording flag
    is_partial = models.BooleanField(
        default=False,
        help_text="True if this is from an interrupted recording (user navigated away)"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pending Capture'
        verbose_name_plural = 'Pending Captures'
        unique_together = ['user', 'client_id']
        indexes = [
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['client_id']),
        ]

    def __str__(self):
        duration_str = f"{self.duration_seconds}s" if self.duration_seconds else "unknown"
        return f"Pending {self.client_id[:8]}... ({duration_str}, {self.get_status_display()})"

    def is_active(self):
        """Check if this pending capture is still active (not completed/abandoned)."""
        return self.status in [
            self.STATUS_PENDING,
            self.STATUS_UPLOADING,
            self.STATUS_UPLOADED,
            self.STATUS_DOWNLOADED,
        ]

    def mark_uploading(self):
        """Mark as currently uploading."""
        from django.utils import timezone
        self.status = self.STATUS_UPLOADING
        self.upload_attempts += 1
        self.last_upload_attempt_at = timezone.now()
        self.save(update_fields=['status', 'upload_attempts', 'last_upload_attempt_at', 'updated_at'])

    def mark_uploaded(self):
        """Mark as uploaded (awaiting processing)."""
        self.status = self.STATUS_UPLOADED
        self.save(update_fields=['status', 'updated_at'])

    def mark_completed(self, capture_entry):
        """Mark as completed and link to CaptureEntry."""
        self.status = self.STATUS_COMPLETED
        self.capture_entry = capture_entry
        self.save(update_fields=['status', 'capture_entry', 'updated_at'])

    def mark_failed(self, error_message):
        """Mark upload as failed with error."""
        self.status = self.STATUS_PENDING  # Back to pending for retry
        self.last_error = error_message
        self.save(update_fields=['status', 'last_error', 'updated_at'])

    def mark_downloaded(self):
        """Mark as downloaded by user (manual backup)."""
        self.status = self.STATUS_DOWNLOADED
        self.save(update_fields=['status', 'updated_at'])

    def mark_abandoned(self):
        """Mark as abandoned (user discarded)."""
        self.status = self.STATUS_ABANDONED
        self.save(update_fields=['status', 'updated_at'])

    def update_heartbeat(self):
        """Update the heartbeat timestamp."""
        from django.utils import timezone
        self.last_heartbeat_at = timezone.now()
        self.save(update_fields=['last_heartbeat_at'])


# =============================================================================
# Phase 5.5: Capture Signal Extraction
# =============================================================================

class CaptureSignal(models.Model):
    """
    NLP-extracted behavioral signal candidate from a capture transcript.

    Created by CaptureSignalExtractor: LLM proposes candidates, deterministic
    validation layer filters/maps them. These records are blended into
    SignalSnapshots by _blend_capture_signals() during signal aggregation.

    The LLM never writes signals directly — this model stores validated
    intermediate extraction results only.
    """

    entry = models.ForeignKey(
        CaptureEntry,
        on_delete=models.CASCADE,
        related_name='extraction_signals',
    )
    signal_type = models.CharField(
        max_length=30,
        help_text='Signal taxonomy type (e.g., health_activity, faith_practice)',
    )
    domain = models.CharField(
        max_length=20,
        help_text='LifeDomain slug (e.g., health, faith)',
    )
    confidence = models.FloatField(
        help_text='Validated extraction confidence 0.0-1.0',
    )
    extracted_text = models.TextField(
        help_text='The phrase from the transcript indicating this behavior',
    )
    direction = models.CharField(
        max_length=10,
        choices=[('positive', 'Positive'), ('negative', 'Negative')],
        default='positive',
        help_text='Positive = behavior occurred, Negative = skipped/missed',
    )
    extractor_type = models.CharField(
        max_length=30,
        help_text='Which extractor produced this (emotional_tone, health_behavior, etc.)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['entry', 'signal_type']),
            models.Index(fields=['entry', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"CaptureSignal({self.signal_type}, {self.confidence:.2f}, "
            f"{self.direction}) for entry {self.entry_id}"
        )
