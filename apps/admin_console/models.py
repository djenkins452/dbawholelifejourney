# ==============================================================================
# File: apps/admin_console/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console models for project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.core.exceptions import ValidationError
from django.db import models


class AdminProjectPhase(models.Model):
    """Project phase for organizing admin tasks."""

    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('complete', 'Complete'),
    ]

    phase_number = models.IntegerField(unique=True)
    name = models.CharField(max_length=100)
    objective = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['phase_number']
        verbose_name = 'Project Phase'
        verbose_name_plural = 'Project Phases'

    def __str__(self):
        return f"Phase {self.phase_number}: {self.name}"

    def clean(self):
        """Validate phase status transitions."""
        if self.pk:
            try:
                old_instance = AdminProjectPhase.objects.get(pk=self.pk)
                # Prevent complete -> in_progress without admin_override flag
                if old_instance.status == 'complete' and self.status == 'in_progress':
                    if not getattr(self, '_admin_override', False):
                        raise ValidationError(
                            "Cannot change a completed phase back to in_progress. "
                            "Use admin override if this is intentional."
                        )
            except AdminProjectPhase.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        """Ensure only one phase is in_progress at a time."""
        self.full_clean()

        # If this phase is being set to in_progress, update other phases
        if self.status == 'in_progress':
            # Set all other non-complete phases to not_started
            AdminProjectPhase.objects.exclude(pk=self.pk).exclude(
                status='complete'
            ).update(status='not_started')

        super().save(*args, **kwargs)

    def set_in_progress_with_override(self):
        """Set phase to in_progress with admin override (even if complete)."""
        self._admin_override = True
        self.status = 'in_progress'
        self.save()
        del self._admin_override


class AdminTask(models.Model):
    """Admin task for project management."""

    CATEGORY_CHOICES = [
        ('feature', 'Feature'),
        ('bug', 'Bug'),
        ('infra', 'Infrastructure'),
        ('content', 'Content'),
        ('business', 'Business'),
    ]

    STATUS_CHOICES = [
        ('backlog', 'Backlog'),
        ('ready', 'Ready'),
        ('in_progress', 'In Progress'),
        ('blocked', 'Blocked'),
        ('done', 'Done'),
    ]

    EFFORT_CHOICES = [
        ('S', 'Small'),
        ('M', 'Medium'),
        ('L', 'Large'),
    ]

    CREATED_BY_CHOICES = [
        ('human', 'Human'),
        ('claude', 'Claude'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority = models.IntegerField(default=3)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='backlog')
    effort = models.CharField(max_length=1, choices=EFFORT_CHOICES)
    phase = models.ForeignKey(
        AdminProjectPhase,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    created_by = models.CharField(max_length=10, choices=CREATED_BY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', '-created_at']
        verbose_name = 'Admin Task'
        verbose_name_plural = 'Admin Tasks'

    def __str__(self):
        return self.title


class AdminActivityLog(models.Model):
    """Activity log for admin task changes."""

    CREATED_BY_CHOICES = [
        ('human', 'Human'),
        ('claude', 'Claude'),
    ]

    task = models.ForeignKey(
        AdminTask,
        on_delete=models.CASCADE,
        related_name='activity_logs'
    )
    action = models.TextField()
    created_by = models.CharField(max_length=10, choices=CREATED_BY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        return f"{self.task.title}: {self.action[:50]}"
