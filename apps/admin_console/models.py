# ==============================================================================
# File: apps/admin_console/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console models for project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

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
