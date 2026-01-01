# ==============================================================================
# File: apps/admin_console/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console models including Claude Task Queue management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import models
from django.utils import timezone


class ClaudeTask(models.Model):
    """
    Task queue for Claude Code sessions.
    Manage bugs, features, ideas, and enhancements through the admin interface.
    Claude reads these tasks and executes them in priority order.
    """

    # Status choices
    STATUS_NEW = 'new'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETE = 'complete'
    STATUS_BLOCKED = 'blocked'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_NEW, 'New'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_BLOCKED, 'Blocked'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Priority choices
    PRIORITY_HIGH = 'high'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_LOW = 'low'

    PRIORITY_CHOICES = [
        (PRIORITY_HIGH, 'HIGH - Bugs, broken features, blocking issues'),
        (PRIORITY_MEDIUM, 'MEDIUM - New features, user-requested enhancements'),
        (PRIORITY_LOW, 'LOW - Ideas, nice-to-haves, future improvements'),
    ]

    # Category choices
    CATEGORY_BUG = 'bug'
    CATEGORY_FEATURE = 'feature'
    CATEGORY_ENHANCEMENT = 'enhancement'
    CATEGORY_IDEA = 'idea'
    CATEGORY_REFACTOR = 'refactor'
    CATEGORY_MAINTENANCE = 'maintenance'
    CATEGORY_CLEANUP = 'cleanup'
    CATEGORY_SECURITY = 'security'
    CATEGORY_PERFORMANCE = 'performance'
    CATEGORY_DOCUMENTATION = 'documentation'

    CATEGORY_CHOICES = [
        (CATEGORY_BUG, 'Bug - Fix broken functionality'),
        (CATEGORY_FEATURE, 'Feature - New functionality'),
        (CATEGORY_ENHANCEMENT, 'Enhancement - Improve existing feature'),
        (CATEGORY_IDEA, 'Idea - Future consideration'),
        (CATEGORY_REFACTOR, 'Refactor - Code restructuring'),
        (CATEGORY_MAINTENANCE, 'Maintenance - System upkeep'),
        (CATEGORY_CLEANUP, 'Cleanup - Remove unused code/files'),
        (CATEGORY_SECURITY, 'Security - Security improvements'),
        (CATEGORY_PERFORMANCE, 'Performance - Speed/efficiency'),
        (CATEGORY_DOCUMENTATION, 'Documentation - Docs updates'),
    ]

    # Core fields
    task_number = models.PositiveIntegerField(
        unique=True,
        help_text="Auto-assigned task number (TASK-XXX)"
    )
    title = models.CharField(
        max_length=200,
        help_text="Brief title for the task"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        db_index=True
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_FEATURE
    )

    # Description and details
    description = models.TextField(
        help_text="Detailed description of what needs to be done"
    )
    acceptance_criteria = models.TextField(
        blank=True,
        help_text="List of criteria to verify task completion (one per line)"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional context, links, or implementation hints"
    )

    # Multi-phase support
    phases = models.TextField(
        blank=True,
        help_text="For multi-phase tasks, list phases (one per line). Leave blank for single-phase tasks."
    )
    current_phase = models.PositiveIntegerField(
        default=0,
        help_text="Current phase number (0 = not started, 1 = phase 1, etc.)"
    )

    # Source tracking
    SOURCE_USER = 'user'
    SOURCE_CLAUDE = 'claude'

    SOURCE_CHOICES = [
        (SOURCE_USER, 'User - Added by Danny'),
        (SOURCE_CLAUDE, 'Claude - Discovered during session'),
    ]

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_USER,
        help_text="Who identified this task"
    )

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    session_label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Claude session that worked on this task"
    )
    completion_notes = models.TextField(
        blank=True,
        help_text="Notes added when task was completed"
    )

    class Meta:
        ordering = [
            # Active tasks first
            models.Case(
                models.When(status='in_progress', then=0),
                models.When(status='new', then=1),
                models.When(status='blocked', then=2),
                default=3,
                output_field=models.IntegerField(),
            ),
            # Then by priority
            models.Case(
                models.When(priority='high', then=0),
                models.When(priority='medium', then=1),
                models.When(priority='low', then=2),
                output_field=models.IntegerField(),
            ),
            # Then by creation date
            'created_at',
        ]
        verbose_name = "Claude Task"
        verbose_name_plural = "Claude Tasks"

    def __str__(self):
        return f"TASK-{self.task_number:03d}: {self.title}"

    def save(self, *args, **kwargs):
        # Auto-assign task number if not set
        if not self.task_number:
            last_task = ClaudeTask.objects.order_by('-task_number').first()
            self.task_number = (last_task.task_number + 1) if last_task else 1

        # Set completed_at when status changes to complete
        if self.status == self.STATUS_COMPLETE and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def task_id(self):
        """Returns formatted task ID like TASK-001"""
        return f"TASK-{self.task_number:03d}"

    @property
    def phase_list(self):
        """Returns phases as a list"""
        if not self.phases:
            return []
        return [p.strip() for p in self.phases.strip().split('\n') if p.strip()]

    @property
    def total_phases(self):
        """Returns total number of phases"""
        return len(self.phase_list)

    @property
    def is_multi_phase(self):
        """Returns True if task has multiple phases"""
        return self.total_phases > 1

    @classmethod
    def get_next_task(cls):
        """Returns the next task to work on (highest priority NEW or IN_PROGRESS)"""
        # First check for in-progress tasks
        in_progress = cls.objects.filter(status=cls.STATUS_IN_PROGRESS).first()
        if in_progress:
            return in_progress

        # Then get highest priority new task
        return cls.objects.filter(status=cls.STATUS_NEW).first()

    @classmethod
    def get_status_summary(cls):
        """Returns a summary of task counts by status"""
        return {
            'active': cls.objects.filter(status=cls.STATUS_IN_PROGRESS).count(),
            'pending': cls.objects.filter(status=cls.STATUS_NEW).count(),
            'blocked': cls.objects.filter(status=cls.STATUS_BLOCKED).count(),
            'complete': cls.objects.filter(status=cls.STATUS_COMPLETE).count(),
            'cancelled': cls.objects.filter(status=cls.STATUS_CANCELLED).count(),
        }
