"""Scan Admin - View scan logs, consents, and image analyses."""

from django.contrib import admin

from .models import ImageAnalysis, ScanConsent, ScanLog


@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    """Admin for scan logs."""

    list_display = [
        'request_id',
        'user',
        'status',
        'category',
        'confidence',
        'processing_time_ms',
        'created_at',
    ]
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['request_id', 'user__email']
    readonly_fields = [
        'request_id',
        'user',
        'status',
        'category',
        'confidence',
        'items_json',
        'action_taken',
        'image_size_kb',
        'image_format',
        'processing_time_ms',
        'error_code',
        'created_at',
        'updated_at',
    ]
    ordering = ['-created_at']

    def has_add_permission(self, request):
        """Disable adding logs manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing logs."""
        return False


@admin.register(ScanConsent)
class ScanConsentAdmin(admin.ModelAdmin):
    """Admin for scan consents."""

    list_display = ['user', 'consented_at', 'consent_version']
    search_fields = ['user__email']
    readonly_fields = ['user', 'consented_at', 'consent_version', 'created_at']
    ordering = ['-consented_at']

    def has_add_permission(self, request):
        """Disable adding consents manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing consents."""
        return False


@admin.register(ImageAnalysis)
class ImageAnalysisAdmin(admin.ModelAdmin):
    """Admin for image analyses."""

    list_display = [
        'id',
        'user',
        'source_type',
        'status',
        'category',
        'summary_short',
        'processing_time_ms',
        'created_at',
    ]
    list_filter = ['status', 'source_type', 'category', 'created_at']
    search_fields = ['user__email', 'summary', 'search_text']
    readonly_fields = [
        'id', 'user', 'source_type', 'content_type', 'object_id',
        'status', 'image_hash', 'summary', 'detailed_description',
        'category', 'confidence', 'objects_identified', 'text_detected',
        'context_clues', 'relevance_tags', 'actionable_insights',
        'raw_response', 'processing_time_ms', 'model_used',
        'input_tokens', 'output_tokens', 'search_text',
        'created_at', 'updated_at',
    ]
    ordering = ['-created_at']

    def summary_short(self, obj):
        return obj.summary[:80] if obj.summary else ''
    summary_short.short_description = 'Summary'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
