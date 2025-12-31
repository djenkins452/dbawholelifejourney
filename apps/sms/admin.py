# ==============================================================================
# File: admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Django admin configuration for SMS models
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""Django admin configuration for SMS notification models."""

from django.contrib import admin
from django.utils.html import format_html

from .models import SMSNotification, SMSResponse


@admin.register(SMSNotification)
class SMSNotificationAdmin(admin.ModelAdmin):
    """Admin configuration for SMS notifications."""

    list_display = [
        'notification_id_short',
        'user_email',
        'category',
        'status_badge',
        'scheduled_for',
        'sent_at',
        'response_code',
    ]
    list_filter = [
        'status',
        'category',
        'scheduled_for',
        'response_processed',
    ]
    search_fields = [
        'user__email',
        'message',
        'twilio_sid',
        'notification_id',
    ]
    readonly_fields = [
        'notification_id',
        'created_at',
        'updated_at',
        'sent_at',
        'delivered_at',
        'failed_at',
        'response_received_at',
    ]
    date_hierarchy = 'scheduled_for'
    ordering = ['-scheduled_for']

    fieldsets = (
        ('Identification', {
            'fields': ('notification_id', 'user', 'category')
        }),
        ('Message', {
            'fields': ('message', 'scheduled_for')
        }),
        ('Status', {
            'fields': ('status', 'sent_at', 'delivered_at', 'failed_at', 'failure_reason')
        }),
        ('Twilio', {
            'fields': ('twilio_sid',),
            'classes': ('collapse',)
        }),
        ('Source Object', {
            'fields': ('content_type', 'object_id'),
            'classes': ('collapse',)
        }),
        ('Response', {
            'fields': ('response_code', 'response_received_at', 'response_processed')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def notification_id_short(self, obj):
        """Display shortened notification ID."""
        return str(obj.notification_id)[:8]
    notification_id_short.short_description = 'ID'

    def user_email(self, obj):
        """Display user email."""
        return obj.user.email
    user_email.short_description = 'User'

    def status_badge(self, obj):
        """Display colored status badge."""
        colors = {
            'pending': '#6b7280',
            'sent': '#3b82f6',
            'delivered': '#10b981',
            'failed': '#ef4444',
            'cancelled': '#9ca3af',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(SMSResponse)
class SMSResponseAdmin(admin.ModelAdmin):
    """Admin configuration for SMS responses."""

    list_display = [
        'response_id_short',
        'from_number',
        'user_email',
        'body_preview',
        'parsed_action',
        'received_at',
        'processed_status',
    ]
    list_filter = [
        'parsed_action',
        'received_at',
    ]
    search_fields = [
        'from_number',
        'body',
        'user__email',
        'twilio_sms_sid',
    ]
    readonly_fields = [
        'response_id',
        'created_at',
        'updated_at',
        'received_at',
        'processed_at',
    ]
    date_hierarchy = 'received_at'
    ordering = ['-received_at']

    fieldsets = (
        ('Identification', {
            'fields': ('response_id', 'notification', 'user')
        }),
        ('Message', {
            'fields': ('from_number', 'body', 'twilio_sms_sid')
        }),
        ('Parsing', {
            'fields': ('parsed_action', 'remind_minutes')
        }),
        ('Processing', {
            'fields': ('received_at', 'processed_at', 'action_taken', 'processing_error')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def response_id_short(self, obj):
        """Display shortened response ID."""
        return str(obj.response_id)[:8]
    response_id_short.short_description = 'ID'

    def user_email(self, obj):
        """Display user email if available."""
        return obj.user.email if obj.user else '-'
    user_email.short_description = 'User'

    def body_preview(self, obj):
        """Display truncated message body."""
        if len(obj.body) > 50:
            return obj.body[:50] + '...'
        return obj.body
    body_preview.short_description = 'Message'

    def processed_status(self, obj):
        """Display processed status with color."""
        if obj.processed_at:
            return format_html(
                '<span style="color: #10b981;">✓ Processed</span>'
            )
        elif obj.processing_error:
            return format_html(
                '<span style="color: #ef4444;">✗ Failed</span>'
            )
        return format_html(
            '<span style="color: #6b7280;">Pending</span>'
        )
    processed_status.short_description = 'Processed'
