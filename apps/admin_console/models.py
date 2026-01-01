# ==============================================================================
# File: apps/admin_console/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console models for project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 10 - Hardening & Fail-Safes)
# ==============================================================================

from django.core.exceptions import ValidationError
from django.db import models


class TaskStatusTransitionError(Exception):
    """Exception raised for invalid task status transitions."""
    pass


class DeletionProtectedError(Exception):
    """Exception raised when attempting to delete a protected resource."""
    pass


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

    def delete(self, *args, **kwargs):
        """
        Prevent deletion if tasks exist for this phase.

        Raises DeletionProtectedError if the phase has any tasks.
        """
        task_count = self.tasks.count()
        if task_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete Phase {self.phase_number} ('{self.name}'). "
                f"It has {task_count} task(s). Delete or reassign tasks first."
            )
        return super().delete(*args, **kwargs)


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

    # Allowed status transitions: from_status -> [allowed_to_statuses]
    ALLOWED_TRANSITIONS = {
        'backlog': ['ready'],
        'ready': ['in_progress'],
        'in_progress': ['done', 'blocked'],
        'blocked': ['ready'],
        'done': [],  # Done is terminal
    }

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
    blocked_reason = models.TextField(blank=True, default='')
    blocking_task = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blocks',
        help_text='The blocker task that is preventing this task from proceeding'
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

    @classmethod
    def is_valid_transition(cls, from_status, to_status):
        """Check if a status transition is allowed."""
        if from_status == to_status:
            return True  # No change
        allowed = cls.ALLOWED_TRANSITIONS.get(from_status, [])
        return to_status in allowed

    def validate_status_transition(self, new_status, reason=None):
        """
        Validate a status transition.

        Raises TaskStatusTransitionError if:
        - Transition is not allowed
        - Moving to in_progress but phase is not active
        - Moving to blocked without a reason

        Args:
            new_status: The target status
            reason: Optional reason (required for blocked status)

        Returns:
            True if valid
        """
        # Check if transition is allowed
        if not self.is_valid_transition(self.status, new_status):
            raise TaskStatusTransitionError(
                f"Cannot transition from '{self.status}' to '{new_status}'. "
                f"Allowed transitions: {self.ALLOWED_TRANSITIONS.get(self.status, [])}"
            )

        # Check if moving to in_progress requires active phase
        if new_status == 'in_progress':
            if self.phase.status != 'in_progress':
                raise TaskStatusTransitionError(
                    f"Cannot move task to 'in_progress'. "
                    f"Phase '{self.phase.name}' is not active (status: {self.phase.status})."
                )

        # Check if blocked requires a reason
        if new_status == 'blocked':
            if not reason:
                raise TaskStatusTransitionError(
                    "Cannot move task to 'blocked' without a reason."
                )

        return True

    def transition_status(self, new_status, reason=None, created_by='human'):
        """
        Transition the task to a new status with validation and logging.

        Args:
            new_status: The target status
            reason: Optional reason (required for blocked status)
            created_by: Who initiated the change ('human' or 'claude')

        Returns:
            The created AdminActivityLog entry

        Raises:
            TaskStatusTransitionError if transition is invalid
        """
        old_status = self.status

        # No-op if status unchanged
        if old_status == new_status:
            return None

        # Validate the transition
        self.validate_status_transition(new_status, reason)

        # Update the task
        self.status = new_status
        if new_status == 'blocked':
            self.blocked_reason = reason
        elif new_status != 'blocked' and self.blocked_reason:
            # Clear blocked reason when leaving blocked state
            self.blocked_reason = ''
        self.save()

        # Create activity log
        if reason:
            action = f"Status changed from '{old_status}' to '{new_status}'. Reason: {reason}"
        else:
            action = f"Status changed from '{old_status}' to '{new_status}'."

        log = AdminActivityLog.objects.create(
            task=self,
            action=action,
            created_by=created_by
        )

        # Phase 8: Auto-unlock - Check phase completion when task transitions to done
        if new_status == 'done':
            from .services import on_task_done
            on_task_done(self, created_by)

        return log

    def delete(self, *args, **kwargs):
        """
        Prevent deletion if task has activity logs.

        Raises DeletionProtectedError if the task has any activity logs.
        """
        log_count = self.activity_logs.count()
        if log_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete task '{self.title}' (ID: {self.pk}). "
                f"It has {log_count} activity log(s). "
                f"Activity logs preserve audit history and cannot be orphaned."
            )
        return super().delete(*args, **kwargs)


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
