"""
Scan Models - Tracking scan requests and results.

Privacy Note: We intentionally do NOT store the raw image.
Only metadata about the scan is logged for analytics and debugging.
"""

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TimeStampedModel


class ScanLog(TimeStampedModel):
    """
    Log of scan requests for analytics and debugging.

    Security: Never stores raw image data. Only metadata.
    """

    # Status choices
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_TIMEOUT = 'timeout'
    STATUS_RATE_LIMITED = 'rate_limited'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_TIMEOUT, 'Timeout'),
        (STATUS_RATE_LIMITED, 'Rate Limited'),
    ]

    # Category choices (what the AI identified)
    CATEGORY_FOOD = 'food'
    CATEGORY_MEDICINE = 'medicine'
    CATEGORY_SUPPLEMENT = 'supplement'
    CATEGORY_RECEIPT = 'receipt'
    CATEGORY_DOCUMENT = 'document'
    CATEGORY_WORKOUT = 'workout_equipment'
    CATEGORY_BARCODE = 'barcode'
    CATEGORY_UNKNOWN = 'unknown'

    CATEGORY_CHOICES = [
        (CATEGORY_FOOD, 'Food'),
        (CATEGORY_MEDICINE, 'Medicine'),
        (CATEGORY_SUPPLEMENT, 'Supplement'),
        (CATEGORY_RECEIPT, 'Receipt'),
        (CATEGORY_DOCUMENT, 'Document'),
        (CATEGORY_WORKOUT, 'Workout Equipment'),
        (CATEGORY_BARCODE, 'Barcode'),
        (CATEGORY_UNKNOWN, 'Unknown'),
    ]

    # Fields
    request_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Unique ID for this scan request"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scan_logs',
        help_text="User who initiated the scan"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Status of the scan request"
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        blank=True,
        help_text="Category identified by AI"
    )

    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="AI confidence score (0.0-1.0)"
    )

    items_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Detected items as JSON array"
    )

    action_taken = models.CharField(
        max_length=100,
        blank=True,
        help_text="What action the user chose (if any)"
    )

    # Technical metadata (for debugging, NOT sensitive)
    image_size_kb = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Size of uploaded image in KB"
    )

    image_format = models.CharField(
        max_length=20,
        blank=True,
        help_text="Image format (jpeg, png, webp)"
    )

    processing_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Time to process in milliseconds"
    )

    error_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Error code if failed"
    )

    # Do NOT store: raw image, user IP, device info (privacy)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Scan Log'
        verbose_name_plural = 'Scan Logs'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['category', '-created_at']),
        ]

    def __str__(self):
        return f"Scan {self.request_id} - {self.category or 'pending'}"

    def mark_success(self, category, confidence, items, processing_time_ms):
        """Mark scan as successful with results."""
        self.status = self.STATUS_SUCCESS
        self.category = category
        self.confidence = confidence
        self.items_json = items
        self.processing_time_ms = processing_time_ms
        self.save(update_fields=[
            'status', 'category', 'confidence', 'items_json',
            'processing_time_ms', 'updated_at'
        ])

    def mark_failed(self, error_code, processing_time_ms=None):
        """Mark scan as failed with error code."""
        self.status = self.STATUS_FAILED
        self.error_code = error_code
        if processing_time_ms:
            self.processing_time_ms = processing_time_ms
        self.save(update_fields=[
            'status', 'error_code', 'processing_time_ms', 'updated_at'
        ])

    def mark_timeout(self, processing_time_ms):
        """Mark scan as timed out."""
        self.status = self.STATUS_TIMEOUT
        self.processing_time_ms = processing_time_ms
        self.error_code = 'TIMEOUT'
        self.save(update_fields=[
            'status', 'error_code', 'processing_time_ms', 'updated_at'
        ])

    def record_action(self, action_id):
        """Record what action the user took."""
        self.action_taken = action_id
        self.save(update_fields=['action_taken', 'updated_at'])


class ScanConsent(TimeStampedModel):
    """
    Records user consent for AI image processing.

    Privacy: Users must consent before their images are sent to OpenAI.
    This is separate from general AI consent for text-based features.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scan_consent',
        help_text="User who gave consent"
    )

    consented_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When consent was given"
    )

    consent_version = models.CharField(
        max_length=10,
        default='1.0',
        help_text="Version of consent terms"
    )

    class Meta:
        verbose_name = 'Scan Consent'
        verbose_name_plural = 'Scan Consents'

    def __str__(self):
        return f"Scan consent for {self.user.email}"


class ImageAnalysis(TimeStampedModel):
    """
    Comprehensive AI analysis of any image in the WLJ ecosystem.

    Stores rich analysis results that feed into CoS context and are
    searchable across the app. Images can come from any source: AI chat,
    camera scan, life module uploads, notes, etc.

    Privacy: No raw image data is stored. Only the analysis results.
    """

    SOURCE_CHOICES = [
        ('chat', 'AI Chat'),
        ('scan', 'Camera Scan'),
        ('inventory', 'Inventory Photo'),
        ('pet', 'Pet Photo'),
        ('recipe', 'Recipe Image'),
        ('project', 'Project Cover'),
        ('document', 'Document'),
        ('note', 'Note Image'),
        ('medical', 'Medical Document'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('analyzing', 'Analyzing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='image_analyses',
    )

    # Source tracking via GenericForeignKey
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source_object = GenericForeignKey('content_type', 'object_id')

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True,
    )

    # Deduplication
    image_hash = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="SHA-256 hash for dedup",
    )

    # Analysis results
    summary = models.TextField(blank=True, help_text="1-2 sentence summary")
    detailed_description = models.TextField(
        blank=True, help_text="Rich natural-language analysis",
    )
    category = models.CharField(
        max_length=30, blank=True, help_text="Best-fit WLJ category",
    )
    confidence = models.FloatField(null=True, blank=True)
    objects_identified = models.JSONField(default=list, blank=True)
    text_detected = models.TextField(blank=True)
    context_clues = models.TextField(blank=True)
    relevance_tags = models.JSONField(default=list, blank=True)
    actionable_insights = models.JSONField(default=list, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    # Performance metadata
    processing_time_ms = models.PositiveIntegerField(null=True, blank=True)
    model_used = models.CharField(max_length=50, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)

    # Denormalized search text
    search_text = models.TextField(
        blank=True, editable=False,
        help_text="Combined text from all analysis fields for search",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Image Analysis'
        verbose_name_plural = 'Image Analyses'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'source_type', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Analysis {self.pk} [{self.source_type}] {self.summary[:60]}"
