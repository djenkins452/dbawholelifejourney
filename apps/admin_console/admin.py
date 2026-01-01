# ==============================================================================
# File: apps/admin_console/admin.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin interface for Claude Task Queue management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.contrib import admin
from django.utils.html import format_html
from .models import ClaudeTask


@admin.register(ClaudeTask)
class ClaudeTaskAdmin(admin.ModelAdmin):
    """
    Admin interface for managing Claude Code tasks.
    Add bugs, features, ideas, and enhancements for Claude to work on.
    """

    list_display = [
        'task_id_display',
        'title',
        'status_badge',
        'priority_badge',
        'category',
        'source_badge',
        'phase_display',
        'created_at',
    ]

    list_filter = [
        'status',
        'priority',
        'category',
        'source',
    ]

    search_fields = [
        'title',
        'description',
        'notes',
    ]

    readonly_fields = [
        'task_number',
        'created_at',
        'updated_at',
        'completed_at',
    ]

    fieldsets = [
        ('Task Info', {
            'fields': [
                'task_number',
                'title',
                ('status', 'priority', 'category'),
                'source',
            ]
        }),
        ('Description', {
            'fields': [
                'description',
                'acceptance_criteria',
                'notes',
            ]
        }),
        ('Multi-Phase (Optional)', {
            'fields': [
                'phases',
                'current_phase',
            ],
            'classes': ['collapse'],
            'description': 'For complex tasks, define phases (one per line). Claude will complete one phase at a time.',
        }),
        ('Tracking', {
            'fields': [
                'session_label',
                'completion_notes',
                ('created_at', 'updated_at', 'completed_at'),
            ],
            'classes': ['collapse'],
        }),
    ]

    ordering = ['-created_at']

    list_per_page = 25

    actions = ['mark_new', 'mark_in_progress', 'mark_complete', 'mark_blocked']

    def task_id_display(self, obj):
        """Display formatted task ID"""
        return obj.task_id
    task_id_display.short_description = 'Task ID'
    task_id_display.admin_order_field = 'task_number'

    def status_badge(self, obj):
        """Display status as colored badge"""
        colors = {
            'new': '#17a2b8',        # blue
            'in_progress': '#ffc107', # yellow
            'complete': '#28a745',    # green
            'blocked': '#dc3545',     # red
            'cancelled': '#6c757d',   # gray
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def priority_badge(self, obj):
        """Display priority as colored badge"""
        colors = {
            'high': '#dc3545',    # red
            'medium': '#ffc107',  # yellow
            'low': '#28a745',     # green
        }
        labels = {
            'high': 'HIGH',
            'medium': 'MED',
            'low': 'LOW',
        }
        color = colors.get(obj.priority, '#6c757d')
        label = labels.get(obj.priority, obj.priority)
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            label
        )
    priority_badge.short_description = 'Priority'
    priority_badge.admin_order_field = 'priority'

    def source_badge(self, obj):
        """Display source as colored badge"""
        colors = {
            'user': '#6f42c1',    # purple
            'claude': '#fd7e14',  # orange
        }
        labels = {
            'user': 'User',
            'claude': 'Claude',
        }
        color = colors.get(obj.source, '#6c757d')
        label = labels.get(obj.source, obj.source)
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            label
        )
    source_badge.short_description = 'Source'
    source_badge.admin_order_field = 'source'

    def phase_display(self, obj):
        """Display current phase progress"""
        if not obj.is_multi_phase:
            return '-'
        return f"{obj.current_phase}/{obj.total_phases}"
    phase_display.short_description = 'Phase'

    @admin.action(description="Mark selected tasks as New")
    def mark_new(self, request, queryset):
        count = queryset.update(status=ClaudeTask.STATUS_NEW)
        self.message_user(request, f"{count} task(s) marked as New.")

    @admin.action(description="Mark selected tasks as In Progress")
    def mark_in_progress(self, request, queryset):
        count = queryset.update(status=ClaudeTask.STATUS_IN_PROGRESS)
        self.message_user(request, f"{count} task(s) marked as In Progress.")

    @admin.action(description="Mark selected tasks as Complete")
    def mark_complete(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(status=ClaudeTask.STATUS_COMPLETE, completed_at=timezone.now())
        self.message_user(request, f"{count} task(s) marked as Complete.")

    @admin.action(description="Mark selected tasks as Blocked")
    def mark_blocked(self, request, queryset):
        count = queryset.update(status=ClaudeTask.STATUS_BLOCKED)
        self.message_user(request, f"{count} task(s) marked as Blocked.")

    def save_model(self, request, obj, form, change):
        """Auto-assign task number on first save"""
        if not obj.task_number:
            last_task = ClaudeTask.objects.order_by('-task_number').first()
            obj.task_number = (last_task.task_number + 1) if last_task else 1
        super().save_model(request, obj, form, change)
