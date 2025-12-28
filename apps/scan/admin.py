"""Scan Admin - View scan logs and consents."""

from django.contrib import admin

from .models import ScanConsent, ScanLog


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
