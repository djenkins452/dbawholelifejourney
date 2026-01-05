"""
Django Admin Configuration for WLJ Personal Assistant System.

Owner: admin@wholelifejourney.com

This module provides admin interface for managing improvement tasks
and monitoring the self-improving assistant system.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import ImprovementTaskModel


@admin.register(ImprovementTaskModel)
class ImprovementTaskModelAdmin(admin.ModelAdmin):
    """Admin interface for ImprovementTaskModel."""

    list_display = [
        'title',
        'gap_type_badge',
        'severity_badge',
        'status_badge',
        'requires_approval',
        'created_at',
        'approved_by',
    ]
    list_filter = [
        'status',
        'gap_type',
        'severity',
        'requires_approval',
        'created_at',
    ]
    search_fields = [
        'title',
        'original_query',
        'suggested_fix',
        'error_message',
    ]
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'approved_at',
        'completed_at',
        'git_commit_before',
        'git_commit_after',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Task Information', {
            'fields': ('id', 'title', 'description', 'original_query')
        }),
        ('Classification', {
            'fields': ('gap_type', 'severity')
        }),
        ('Implementation', {
            'fields': ('suggested_fix', 'code_template', 'test_template'),
            'classes': ('collapse',)
        }),
        ('Workflow', {
            'fields': ('requires_approval', 'status', 'error_message')
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Git Tracking', {
            'fields': ('git_commit_before', 'git_commit_after'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

    def gap_type_badge(self, obj):
        """Display gap type with color-coded badge."""
        colors = {
            'unknown_data_type': '#dc3545',  # Red
            'missing_keywords': '#28a745',   # Green
            'no_data_method': '#ffc107',     # Yellow
            'unsupported_query_pattern': '#dc3545',  # Red
        }
        color = colors.get(obj.gap_type, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_gap_type_display()
        )
    gap_type_badge.short_description = 'Gap Type'
    gap_type_badge.admin_order_field = 'gap_type'

    def severity_badge(self, obj):
        """Display severity with color-coded badge."""
        colors = {
            'low': '#28a745',     # Green
            'medium': '#ffc107',  # Yellow
            'high': '#dc3545',    # Red
        }
        color = colors.get(obj.severity, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_severity_display()
        )
    severity_badge.short_description = 'Severity'
    severity_badge.admin_order_field = 'severity'

    def status_badge(self, obj):
        """Display status with color-coded badge."""
        colors = {
            'new': '#17a2b8',              # Info blue
            'pending_approval': '#ffc107', # Yellow
            'approved': '#28a745',         # Green
            'in_progress': '#007bff',      # Primary blue
            'testing': '#6610f2',          # Purple
            'completed': '#28a745',        # Green
            'error': '#dc3545',            # Red
            'rolled_back': '#6c757d',      # Gray
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    actions = ['approve_tasks', 'reset_to_new']

    @admin.action(description='Approve selected tasks')
    def approve_tasks(self, request, queryset):
        """Bulk approve tasks that are pending approval."""
        approved_count = 0
        for task in queryset.filter(status=ImprovementTaskModel.STATUS_PENDING_APPROVAL):
            try:
                task.transition_status(
                    ImprovementTaskModel.STATUS_APPROVED,
                    user=request.user
                )
                approved_count += 1
            except Exception:
                pass
        self.message_user(request, f'{approved_count} task(s) approved.')

    @admin.action(description='Reset selected tasks to New')
    def reset_to_new(self, request, queryset):
        """Reset tasks to new status (for error recovery)."""
        reset_count = 0
        for task in queryset:
            if task.status in [
                ImprovementTaskModel.STATUS_ERROR,
                ImprovementTaskModel.STATUS_ROLLED_BACK
            ]:
                try:
                    task.transition_status(ImprovementTaskModel.STATUS_NEW)
                    reset_count += 1
                except Exception:
                    pass
        self.message_user(request, f'{reset_count} task(s) reset to New.')
