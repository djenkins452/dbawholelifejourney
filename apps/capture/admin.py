"""Capture admin configuration."""

from django.contrib import admin

from .models import CaptureEntry


@admin.register(CaptureEntry)
class CaptureEntryAdmin(admin.ModelAdmin):
    """Admin for capture entries."""

    list_display = [
        'title',
        'user',
        'status',
        'category',
        'subcategory',
        'duration_seconds',
        'created_at',
    ]
    list_filter = ['status', 'category', 'subcategory', 'created_at']
    search_fields = ['title', 'user__email', 'transcript', 'summary']
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
    ]
    ordering = ['-created_at']

    fieldsets = (
        (None, {
            'fields': ('id', 'user', 'title', 'status')
        }),
        ('Audio', {
            'fields': ('duration_seconds', 'audio_file_url', 'audio_expires_at')
        }),
        ('Content', {
            'fields': ('transcript', 'summary'),
            'classes': ('collapse',)
        }),
        ('Classification', {
            'fields': ('category', 'subcategory')
        }),
        ('Error Info', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
