# ==============================================================================
# File: apps/admin_console/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console models for project task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 17.5 - Executable Task Standard)
# ==============================================================================

from django.core.exceptions import ValidationError
from django.db import models


class TaskStatusTransitionError(Exception):
    """Exception raised for invalid task status transitions."""
    pass


class DeletionProtectedError(Exception):
    """Exception raised when attempting to delete a protected resource."""
    pass


class ExecutableTaskValidationError(ValidationError):
    """
    Exception raised when a task description does not meet the Executable Task Standard.

    The Executable Task Standard requires all tasks to have a description JSONField
    with the following mandatory keys:
    - objective (string): What the task should accomplish
    - inputs (array of strings): Required context or resources to complete the task
    - actions (array of strings, at least one): Step-by-step actions to execute
    - output (string): Expected deliverable or result
    """
    pass


def validate_executable_task_description(value):
    """
    Validate that a task description conforms to the Executable Task Standard.

    Required structure:
    {
        "objective": "string - what the task should accomplish",
        "inputs": ["array", "of", "strings"],
        "actions": ["at least one action step"],
        "output": "string - expected deliverable"
    }

    Raises:
        ExecutableTaskValidationError: If any required field is missing or malformed
    """
    # Skip validation for legacy string descriptions during migration period
    if isinstance(value, str):
        # Legacy format - allow during transition but log warning
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"Legacy string description detected. "
            f"Please migrate to executable task format: {value[:100]}..."
        )
        return  # Allow legacy format during migration

    if not isinstance(value, dict):
        raise ExecutableTaskValidationError(
            "Task description must be a JSON object with objective, inputs, actions, and output fields.",
            code='invalid_type'
        )

    errors = []

    # Validate 'objective' - required string
    if 'objective' not in value:
        errors.append("Missing required field: 'objective'. Provide a clear description of what the task should accomplish.")
    elif not isinstance(value['objective'], str):
        errors.append("Field 'objective' must be a string.")
    elif not value['objective'].strip():
        errors.append("Field 'objective' cannot be empty.")

    # Validate 'inputs' - required array of strings
    if 'inputs' not in value:
        errors.append("Missing required field: 'inputs'. Provide an array of required context or resources (can be empty array []).")
    elif not isinstance(value['inputs'], list):
        errors.append("Field 'inputs' must be an array of strings.")
    else:
        for i, item in enumerate(value['inputs']):
            if not isinstance(item, str):
                errors.append(f"Field 'inputs[{i}]' must be a string, got {type(item).__name__}.")

    # Validate 'actions' - required non-empty array of strings
    if 'actions' not in value:
        errors.append("Missing required field: 'actions'. Provide at least one action step for AI to execute.")
    elif not isinstance(value['actions'], list):
        errors.append("Field 'actions' must be an array of strings.")
    elif len(value['actions']) == 0:
        errors.append("Field 'actions' must contain at least one action step. Tasks without actions cannot be executed.")
    else:
        for i, item in enumerate(value['actions']):
            if not isinstance(item, str):
                errors.append(f"Field 'actions[{i}]' must be a string, got {type(item).__name__}.")
            elif not item.strip():
                errors.append(f"Field 'actions[{i}]' cannot be empty.")

    # Validate 'output' - required string
    if 'output' not in value:
        errors.append("Missing required field: 'output'. Specify the expected deliverable or result.")
    elif not isinstance(value['output'], str):
        errors.append("Field 'output' must be a string.")
    elif not value['output'].strip():
        errors.append("Field 'output' cannot be empty.")

    if errors:
        raise ExecutableTaskValidationError(errors, code='invalid_structure')


# ==============================================================================
# Phase 17: Task Field Configuration Models
# ==============================================================================

class AdminTaskStatusConfig(models.Model):
    """
    Configuration for task status values.

    Replaces hardcoded STATUS_CHOICES with database-driven configuration.
    Allows admin to define custom status values with execution semantics.
    """
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    execution_allowed = models.BooleanField(
        default=False,
        help_text='If True, tasks in this status can be executed/worked on'
    )
    terminal = models.BooleanField(
        default=False,
        help_text='If True, this is a terminal status (no further transitions allowed)'
    )
    order = models.IntegerField(default=0, help_text='Display order in dropdowns')
    active = models.BooleanField(default=True, help_text='If False, cannot be assigned to new tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Task Status Config'
        verbose_name_plural = 'Task Status Configs'

    def __str__(self):
        return self.display_name

    def delete(self, *args, **kwargs):
        """Prevent deletion if status is in use by tasks."""
        from django.db.models import Q
        task_count = AdminTask.objects.filter(
            Q(status_config=self) | Q(status=self.name)
        ).count()
        if task_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete status '{self.name}'. "
                f"It is used by {task_count} task(s)."
            )
        return super().delete(*args, **kwargs)


class AdminTaskPriorityConfig(models.Model):
    """
    Configuration for task priority values.

    Replaces hardcoded priority integer range with database-driven configuration.
    """
    label = models.CharField(max_length=50, help_text='Display label, e.g., "Highest"')
    value = models.IntegerField(unique=True, help_text='Numeric value, e.g., 1 for highest')
    order = models.IntegerField(default=0, help_text='Display order in dropdowns')
    active = models.BooleanField(default=True, help_text='If False, cannot be assigned to new tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'value']
        verbose_name = 'Task Priority Config'
        verbose_name_plural = 'Task Priority Configs'

    def __str__(self):
        return f"{self.value} - {self.label}"

    def delete(self, *args, **kwargs):
        """Prevent deletion if priority is in use by tasks."""
        from django.db.models import Q
        task_count = AdminTask.objects.filter(
            Q(priority_config=self) | Q(priority=self.value)
        ).count()
        if task_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete priority '{self.label}'. "
                f"It is used by {task_count} task(s)."
            )
        return super().delete(*args, **kwargs)


class AdminTaskCategoryConfig(models.Model):
    """
    Configuration for task category values.

    Replaces hardcoded CATEGORY_CHOICES with database-driven configuration.
    """
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    order = models.IntegerField(default=0, help_text='Display order in dropdowns')
    active = models.BooleanField(default=True, help_text='If False, cannot be assigned to new tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Task Category Config'
        verbose_name_plural = 'Task Category Configs'

    def __str__(self):
        return self.display_name

    def delete(self, *args, **kwargs):
        """Prevent deletion if category is in use by tasks."""
        from django.db.models import Q
        task_count = AdminTask.objects.filter(
            Q(category_config=self) | Q(category=self.name)
        ).count()
        if task_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete category '{self.name}'. "
                f"It is used by {task_count} task(s)."
            )
        return super().delete(*args, **kwargs)


class AdminTaskEffortConfig(models.Model):
    """
    Configuration for task effort/size values.

    Replaces hardcoded EFFORT_CHOICES with database-driven configuration.
    """
    label = models.CharField(max_length=50, help_text='Display label, e.g., "Small"')
    value = models.CharField(max_length=10, unique=True, help_text='Short code, e.g., "S"')
    order = models.IntegerField(default=0, help_text='Display order in dropdowns')
    active = models.BooleanField(default=True, help_text='If False, cannot be assigned to new tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'value']
        verbose_name = 'Task Effort Config'
        verbose_name_plural = 'Task Effort Configs'

    def __str__(self):
        return f"{self.value} - {self.label}"

    def delete(self, *args, **kwargs):
        """Prevent deletion if effort is in use by tasks."""
        from django.db.models import Q
        task_count = AdminTask.objects.filter(
            Q(effort_config=self) | Q(effort=self.value)
        ).count()
        if task_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete effort '{self.label}'. "
                f"It is used by {task_count} task(s)."
            )
        return super().delete(*args, **kwargs)


class AdminProject(models.Model):
    """
    Project model for organizing admin tasks.

    Projects are first-class objects that group related tasks together.
    Each task must belong to a project.
    """

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('complete', 'Complete'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Admin Project'
        verbose_name_plural = 'Admin Projects'

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        """
        Prevent deletion if tasks exist for this project.

        Raises DeletionProtectedError if the project has any tasks.
        """
        task_count = self.tasks.count()
        if task_count > 0:
            raise DeletionProtectedError(
                f"Cannot delete project '{self.name}' (ID: {self.pk}). "
                f"It has {task_count} task(s). Delete or reassign tasks first."
            )
        return super().delete(*args, **kwargs)


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
    """
    Admin task for project management.

    WLJ EXECUTABLE TASK STANDARD:
    All tasks must have a description JSONField with the following required structure:
    {
        "objective": "What the task should accomplish",
        "inputs": ["Required context", "resources", "or dependencies"],
        "actions": ["Step 1: Do this", "Step 2: Then this"],
        "output": "Expected deliverable or result"
    }

    Tasks that do not conform to this structure cannot be saved.
    """

    # Legacy choices - kept for backward compatibility during migration
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

    # Executable Task Description - JSONField with required structure
    # Structure: {objective: str, inputs: [str], actions: [str], output: str}
    description = models.JSONField(
        validators=[validate_executable_task_description],
        help_text=(
            'Executable task description in JSON format. Required fields: '
            'objective (string), inputs (array of strings), '
            'actions (array with at least one step), output (string).'
        ),
        default=dict
    )

    # Legacy fields (kept for backward compatibility)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority = models.IntegerField(default=3)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='backlog')
    effort = models.CharField(max_length=10, choices=EFFORT_CHOICES)

    # Phase 17: Config ForeignKey fields (nullable during migration)
    status_config = models.ForeignKey(
        AdminTaskStatusConfig,
        on_delete=models.PROTECT,
        related_name='tasks',
        null=True,
        blank=True,
        help_text='Configured status for this task'
    )
    priority_config = models.ForeignKey(
        AdminTaskPriorityConfig,
        on_delete=models.PROTECT,
        related_name='tasks',
        null=True,
        blank=True,
        help_text='Configured priority for this task'
    )
    category_config = models.ForeignKey(
        AdminTaskCategoryConfig,
        on_delete=models.PROTECT,
        related_name='tasks',
        null=True,
        blank=True,
        help_text='Configured category for this task'
    )
    effort_config = models.ForeignKey(
        AdminTaskEffortConfig,
        on_delete=models.PROTECT,
        related_name='tasks',
        null=True,
        blank=True,
        help_text='Configured effort level for this task'
    )

    phase = models.ForeignKey(
        AdminProjectPhase,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    project = models.ForeignKey(
        AdminProject,
        on_delete=models.PROTECT,
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
    attachment = models.ImageField(
        upload_to='admin_tasks/attachments/',
        null=True,
        blank=True,
        help_text='Optional screenshot or image attachment for task context'
    )
    created_by = models.CharField(max_length=10, choices=CREATED_BY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_status_display_value(self):
        """Get the display value for status from config or legacy field."""
        if self.status_config:
            return self.status_config.display_name
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    def get_priority_display_value(self):
        """Get the display value for priority from config or legacy field."""
        if self.priority_config:
            return self.priority_config.label
        return str(self.priority)

    def get_category_display_value(self):
        """Get the display value for category from config or legacy field."""
        if self.category_config:
            return self.category_config.display_name
        return dict(self.CATEGORY_CHOICES).get(self.category, self.category)

    def get_effort_display_value(self):
        """Get the display value for effort from config or legacy field."""
        if self.effort_config:
            return self.effort_config.label
        return dict(self.EFFORT_CHOICES).get(self.effort, self.effort)

    class Meta:
        ordering = ['priority', '-created_at']
        verbose_name = 'Admin Task'
        verbose_name_plural = 'Admin Tasks'

    def __str__(self):
        return self.title

    # Class attribute to control validation during tests
    _skip_executable_validation = False

    def clean(self):
        """
        Validate the task before saving.

        Enforces the Executable Task Standard by validating the description field.
        Set _skip_executable_validation = True to bypass during legacy data migration.
        """
        super().clean()
        # Skip validation if explicitly bypassed (e.g., data migrations)
        if not self._skip_executable_validation:
            validate_executable_task_description(self.description)

    def save(self, *args, **kwargs):
        """
        Save the task with validation.

        Runs full_clean() to ensure the Executable Task Standard is enforced,
        unless skip_validation=True is passed.
        """
        skip_validation = kwargs.pop('skip_validation', False)
        if not skip_validation:
            self.full_clean()
        super().save(*args, **kwargs)

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
        # Phase 16: Also check project completion
        if new_status == 'done':
            from .services import on_task_done, on_task_done_check_project
            on_task_done(self, created_by)
            on_task_done_check_project(self, created_by)

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
