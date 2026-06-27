# ==============================================================================
# File: apps/admin_console/models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console models for project task management
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-01
# Last Updated: 2026-01-03 (Added DataLoadConfig for one-time data loading)
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

    PRIORITY_CHOICES = [(i, str(i)) for i in range(1, 11)]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.PositiveIntegerField(
        choices=PRIORITY_CHOICES,
        default=5,
        help_text='Project priority (1=highest, 10=lowest)'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', 'name']
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
        return self.name

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
        ('404_reporter', '404 Reporter'),
        ('system', 'System'),
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
    resolution_notes = models.TextField(
        blank=True,
        default='',
        help_text='Documentation of what was done to complete this task: root cause, fix applied, files changed, etc.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the task was marked as done'
    )
    created_by = models.CharField(max_length=15, choices=CREATED_BY_CHOICES)
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

        # Check if blocked requires a reason
        if new_status == 'blocked':
            if not reason:
                raise TaskStatusTransitionError(
                    "Cannot move task to 'blocked' without a reason."
                )

        return True

    def transition_status(self, new_status, reason=None, created_by='human', resolution_notes=None):
        """
        Transition the task to a new status with validation and logging.

        Args:
            new_status: The target status
            reason: Optional reason (required for blocked status)
            created_by: Who initiated the change ('human' or 'claude')
            resolution_notes: Documentation of what was done to complete the task

        Returns:
            The created AdminActivityLog entry

        Raises:
            TaskStatusTransitionError if transition is invalid
        """
        from django.utils import timezone

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

        # Set resolution notes and completed_at when transitioning to done
        if new_status == 'done':
            if resolution_notes:
                self.resolution_notes = resolution_notes
            self.completed_at = timezone.now()

        self.save()

        # Create activity log
        if reason:
            action = f"Status changed from '{old_status}' to '{new_status}'. Reason: {reason}"
        else:
            action = f"Status changed from '{old_status}' to '{new_status}'."

        # Include resolution notes in activity log if provided
        if resolution_notes and new_status == 'done':
            action += f"\n\nResolution: {resolution_notes}"

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
        ('404_reporter', '404 Reporter'),
        ('system', 'System'),
    ]

    task = models.ForeignKey(
        AdminTask,
        on_delete=models.CASCADE,
        related_name='activity_logs'
    )
    action = models.TextField()
    created_by = models.CharField(max_length=15, choices=CREATED_BY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        return f"{self.task.title}: {self.action[:50]}"


class DataLoadConfig(models.Model):
    """
    Tracks which data loaders have been run to prevent redundant loading.

    Each data loader (fixtures, populate commands) registers here when it completes
    successfully. On subsequent deploys, load_initial_data checks this table and
    skips loaders that have already run.

    Admins can:
    - View which loaders have run
    - Reset a loader to force it to run again
    - Manually mark a loader as complete
    """

    LOADER_TYPE_CHOICES = [
        ('fixture', 'Django Fixture'),
        ('command', 'Management Command'),
        ('blueprint', 'Project Blueprint'),
    ]

    # Unique identifier for the loader (e.g., 'categories', 'populate_choices')
    loader_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier for this data loader"
    )
    display_name = models.CharField(
        max_length=200,
        help_text="Human-readable name"
    )
    loader_type = models.CharField(
        max_length=20,
        choices=LOADER_TYPE_CHOICES,
        default='fixture'
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this loader does"
    )

    # Status tracking
    is_loaded = models.BooleanField(
        default=False,
        help_text="Whether this loader has been run successfully"
    )
    loaded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the loader was last run"
    )
    loaded_by = models.CharField(
        max_length=50,
        blank=True,
        help_text="What triggered the load (startup, manual, migration)"
    )

    # Optional: track what was loaded
    records_created = models.PositiveIntegerField(
        default=0,
        help_text="Number of records created by this loader"
    )
    records_updated = models.PositiveIntegerField(
        default=0,
        help_text="Number of records updated by this loader"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['loader_type', 'loader_name']
        verbose_name = 'Data Load Config'
        verbose_name_plural = 'Data Load Configs'

    def __str__(self):
        status = "✓" if self.is_loaded else "○"
        return f"{status} {self.display_name}"

    def mark_loaded(self, loaded_by='startup', records_created=0, records_updated=0):
        """Mark this loader as having been run successfully."""
        from django.utils import timezone
        self.is_loaded = True
        self.loaded_at = timezone.now()
        self.loaded_by = loaded_by
        self.records_created = records_created
        self.records_updated = records_updated
        self.save()

    def reset(self):
        """Reset this loader so it will run again on next startup."""
        self.is_loaded = False
        self.loaded_at = None
        self.loaded_by = ''
        self.records_created = 0
        self.records_updated = 0
        self.save()

    @classmethod
    def is_loader_complete(cls, loader_name):
        """Check if a specific loader has already been run."""
        try:
            config = cls.objects.get(loader_name=loader_name)
            return config.is_loaded
        except cls.DoesNotExist:
            return False

    @classmethod
    def register_loader(cls, loader_name, display_name, loader_type='fixture', description=''):
        """Register a new loader config entry (idempotent)."""
        config, created = cls.objects.get_or_create(
            loader_name=loader_name,
            defaults={
                'display_name': display_name,
                'loader_type': loader_type,
                'description': description,
            }
        )
        return config


class EmailNotificationTemplate(models.Model):
    """
    Admin-editable email notification templates.

    Each category can have a custom email template that administrators can
    modify without code changes. Templates use Django template syntax with
    predefined context variables.

    Available context variables:
    - user: The User object
    - notification: The Notification object
    - notifications: List of notifications (for digest emails)
    - site_name: From SiteConfiguration
    - current_year: Current year for footer
    """

    # Category choices - matches Notification categories
    CATEGORY_MEDICINE = 'medicine'
    CATEGORY_MEDICINE_REFILL = 'medicine_refill'
    CATEGORY_TASK = 'task'
    CATEGORY_EVENT = 'event'
    CATEGORY_PRAYER = 'prayer'
    CATEGORY_READING_PLAN = 'reading_plan'
    CATEGORY_FASTING = 'fasting'
    CATEGORY_SIGNIFICANT_EVENT = 'significant_event'
    CATEGORY_MILESTONE = 'milestone'
    CATEGORY_FINANCE = 'finance'
    CATEGORY_JOURNAL = 'journal'
    CATEGORY_SYSTEM = 'system'
    CATEGORY_DIGEST = 'digest'  # Special category for daily digest

    CATEGORY_CHOICES = [
        (CATEGORY_MEDICINE, 'Medicine Reminder'),
        (CATEGORY_MEDICINE_REFILL, 'Medicine Refill'),
        (CATEGORY_TASK, 'Task Due'),
        (CATEGORY_EVENT, 'Calendar Event'),
        (CATEGORY_PRAYER, 'Prayer Reminder'),
        (CATEGORY_READING_PLAN, 'Reading Plan'),
        (CATEGORY_FASTING, 'Fasting Reminder'),
        (CATEGORY_SIGNIFICANT_EVENT, 'Significant Event'),
        (CATEGORY_MILESTONE, 'Goal Milestone'),
        (CATEGORY_FINANCE, 'Finance Alert'),
        (CATEGORY_JOURNAL, 'Journal Prompt'),
        (CATEGORY_SYSTEM, 'System'),
        (CATEGORY_DIGEST, 'Daily Digest'),
    ]

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        unique=True,
        help_text="Notification category this template applies to"
    )

    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name for admin interface"
    )

    subject_template = models.CharField(
        max_length=200,
        help_text="Email subject line. Supports Django template syntax: {{ notification.title }}"
    )

    body_template = models.TextField(
        help_text=(
            "Email body in HTML format. Supports Django template syntax.\n"
            "Available variables: user, notification, notifications (for digest), "
            "site_name, current_year, preferences_url"
        )
    )

    is_active = models.BooleanField(
        default=True,
        help_text="If disabled, emails for this category won't be sent"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category']
        verbose_name = 'Email Notification Template'
        verbose_name_plural = 'Email Notification Templates'

    def __str__(self):
        status = "✓" if self.is_active else "○"
        return f"{status} {self.display_name}"

    def render_subject(self, context):
        """Render the subject template with the given context."""
        from django.template import Template, Context
        template = Template(self.subject_template)
        return template.render(Context(context))

    def render_body(self, context):
        """Render the body template with the given context."""
        from django.template import Template, Context
        template = Template(self.body_template)
        return template.render(Context(context))

    @classmethod
    def get_template_for_category(cls, category):
        """Get the active template for a category, or None if not found/inactive."""
        try:
            template = cls.objects.get(category=category, is_active=True)
            return template
        except cls.DoesNotExist:
            return None


class SystemAnnouncement(models.Model):
    """
    System-wide announcements that display to all users as a modal popup.

    Used for maintenance notifications, feature announcements, important updates, etc.
    Admins can schedule announcements with start/end dates.
    Users can dismiss announcements, tracked via SystemAnnouncementDismissal.
    """

    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_ERROR = 'error'
    SEVERITY_SUCCESS = 'success'
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, 'Info'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_ERROR, 'Error/Urgent'),
        (SEVERITY_SUCCESS, 'Success'),
    ]

    title = models.CharField(
        max_length=200,
        help_text="Short title for the announcement"
    )
    message = models.TextField(
        help_text="Full message content (supports basic HTML: <b>, <i>, <a>, <br>, <ul>, <li>)"
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        help_text="Determines the color/styling of the announcement"
    )

    # Scheduling
    starts_at = models.DateTimeField(
        help_text="When to start showing this announcement"
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to stop showing (leave blank for indefinite)"
    )

    # Publishing
    is_published = models.BooleanField(
        default=False,
        help_text="Only published announcements are shown to users"
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_announcements'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-starts_at', '-created_at']
        verbose_name = "System Announcement"
        verbose_name_plural = "System Announcements"

    def __str__(self):
        return f"{self.title} ({self.get_severity_display()})"

    @property
    def is_active(self):
        """Check if announcement is currently active (published and within date range)."""
        from django.utils import timezone
        now = timezone.now()
        if not self.is_published:
            return False
        if now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    @classmethod
    def get_active_announcements(cls):
        """Get all currently active announcements."""
        from django.utils import timezone
        now = timezone.now()
        return cls.objects.filter(
            is_published=True,
            starts_at__lte=now
        ).filter(
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now)
        ).order_by('-severity', '-starts_at')

    @classmethod
    def get_active_for_user(cls, user):
        """Get active announcements that the user hasn't dismissed."""
        active = cls.get_active_announcements()
        dismissed_ids = SystemAnnouncementDismissal.objects.filter(
            user=user
        ).values_list('announcement_id', flat=True)
        return active.exclude(id__in=dismissed_ids)


class SystemAnnouncementDismissal(models.Model):
    """
    Tracks which users have dismissed which announcements.

    Once a user dismisses an announcement, they won't see it again
    (even if it's still active).
    """

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='dismissed_announcements'
    )
    announcement = models.ForeignKey(
        SystemAnnouncement,
        on_delete=models.CASCADE,
        related_name='dismissals'
    )
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'announcement')
        verbose_name = "Announcement Dismissal"
        verbose_name_plural = "Announcement Dismissals"

    def __str__(self):
        return f"{self.user} dismissed {self.announcement}"


# ==============================================================================
# Production Test Plan Models
# ==============================================================================


class TestCycle(models.Model):
    """
    A test cycle represents a complete testing run for a release.

    Each cycle contains phases (groups of related tests) and items
    (individual test steps). Cycles can be created from templates
    and reused across releases.
    """

    STATUS_DRAFT = 'draft'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_PAUSED = 'paused'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    name = models.CharField(
        max_length=200,
        help_text="Name of this test cycle (e.g., 'v1.0 Production Release')"
    )
    version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Version being tested (e.g., '1.0.0')"
    )
    description = models.TextField(
        blank=True,
        help_text="Description or notes about this test cycle"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )

    # Tracking
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_test_cycles'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When testing started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When all tests were completed"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Test Cycle'
        verbose_name_plural = 'Test Cycles'

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def progress(self):
        """Calculate overall progress as percentage."""
        total = self.items.count()
        if total == 0:
            return 0
        passed = self.items.filter(status=TestItem.STATUS_PASSED).count()
        return int((passed / total) * 100)

    @property
    def stats(self):
        """Get test statistics for this cycle."""
        items = self.items.all()
        return {
            'total': items.count(),
            'not_started': items.filter(status=TestItem.STATUS_NOT_STARTED).count(),
            'in_progress': items.filter(status=TestItem.STATUS_IN_PROGRESS).count(),
            'passed': items.filter(status=TestItem.STATUS_PASSED).count(),
            'failed': items.filter(status=TestItem.STATUS_FAILED).count(),
            'blocked': items.filter(status=TestItem.STATUS_BLOCKED).count(),
        }

    def start(self):
        """Mark this cycle as in progress."""
        from django.utils import timezone
        if self.status == self.STATUS_DRAFT:
            self.status = self.STATUS_IN_PROGRESS
            self.started_at = timezone.now()
            self.save()

    def complete(self):
        """Mark this cycle as completed."""
        from django.utils import timezone
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.save()

    def pause(self):
        """Pause this cycle. Can only pause an in-progress cycle."""
        if self.status == self.STATUS_IN_PROGRESS:
            self.status = self.STATUS_PAUSED
            self.save()

    def resume(self):
        """Resume a paused cycle back to in-progress."""
        if self.status == self.STATUS_PAUSED:
            self.status = self.STATUS_IN_PROGRESS
            self.save()

    def cancel(self):
        """Cancel this cycle. Can cancel from in-progress or paused."""
        from django.utils import timezone
        if self.status in (self.STATUS_IN_PROGRESS, self.STATUS_PAUSED):
            self.status = self.STATUS_CANCELLED
            self.completed_at = timezone.now()
            self.save()


class TestPhase(models.Model):
    """
    A phase groups related test items together.

    Phases represent functional areas (e.g., 'Authentication',
    'Journal Module', 'Health Tracking').
    """

    cycle = models.ForeignKey(
        TestCycle,
        on_delete=models.CASCADE,
        related_name='phases'
    )
    name = models.CharField(
        max_length=200,
        help_text="Phase name (e.g., 'User Authentication')"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this phase tests"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within the cycle"
    )

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Test Phase'
        verbose_name_plural = 'Test Phases'

    def __str__(self):
        return f"{self.cycle.name} - {self.name}"

    @property
    def status(self):
        """Compute phase status from items."""
        items = self.items.all()
        if not items.exists():
            return 'empty'

        statuses = set(items.values_list('status', flat=True))

        # All passed = completed
        if statuses == {TestItem.STATUS_PASSED}:
            return 'completed'

        # Any failed = failed
        if TestItem.STATUS_FAILED in statuses:
            return 'failed'

        # Any blocked = blocked
        if TestItem.STATUS_BLOCKED in statuses:
            return 'blocked'

        # Any in progress or mix of started/not started = in progress
        if TestItem.STATUS_IN_PROGRESS in statuses:
            return 'in_progress'

        # Some passed, some not started = in progress
        if TestItem.STATUS_PASSED in statuses:
            return 'in_progress'

        # All not started = not started
        return 'not_started'

    @property
    def progress(self):
        """Calculate phase progress as percentage."""
        total = self.items.count()
        if total == 0:
            return 0
        passed = self.items.filter(status=TestItem.STATUS_PASSED).count()
        return int((passed / total) * 100)

    @property
    def stats(self):
        """Get test statistics for this phase."""
        items = self.items.all()
        return {
            'total': items.count(),
            'not_started': items.filter(status=TestItem.STATUS_NOT_STARTED).count(),
            'in_progress': items.filter(status=TestItem.STATUS_IN_PROGRESS).count(),
            'passed': items.filter(status=TestItem.STATUS_PASSED).count(),
            'failed': items.filter(status=TestItem.STATUS_FAILED).count(),
            'blocked': items.filter(status=TestItem.STATUS_BLOCKED).count(),
        }


class TestItem(models.Model):
    """
    An individual test step within a phase.

    Each item has an expected result (pre-populated) and fields
    for recording actual results during testing.
    """

    STATUS_NOT_STARTED = 'not_started'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_PASSED = 'passed'
    STATUS_FAILED = 'failed'
    STATUS_BLOCKED = 'blocked'
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, 'Not Started'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_PASSED, 'Passed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_BLOCKED, 'Blocked'),
    ]

    PRIORITY_CRITICAL = 'critical'
    PRIORITY_HIGH = 'high'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_LOW = 'low'
    PRIORITY_CHOICES = [
        (PRIORITY_CRITICAL, 'Critical'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_LOW, 'Low'),
    ]

    # Relationships
    phase = models.ForeignKey(
        TestPhase,
        on_delete=models.CASCADE,
        related_name='items'
    )
    cycle = models.ForeignKey(
        TestCycle,
        on_delete=models.CASCADE,
        related_name='items'
    )

    # Test definition
    name = models.CharField(
        max_length=300,
        help_text="Test name/action (e.g., 'Create new journal entry with image')"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description or steps to perform"
    )
    expected_result = models.TextField(
        blank=True,
        help_text="What should happen when test passes"
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL path to test (e.g., '/journal/new/')"
    )

    # Test execution
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOT_STARTED
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM
    )
    actual_result = models.TextField(
        blank=True,
        help_text="What actually happened during testing"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes, bug references, etc."
    )

    # Tester tracking
    tester = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tested_items'
    )
    tested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the test was last executed"
    )

    # Ordering
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within the phase"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Test Item'
        verbose_name_plural = 'Test Items'

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Auto-set tested_at when status changes to passed/failed
        if self.pk:
            try:
                old = TestItem.objects.get(pk=self.pk)
                if old.status != self.status and self.status in [
                    self.STATUS_PASSED,
                    self.STATUS_FAILED,
                    self.STATUS_BLOCKED,
                ]:
                    from django.utils import timezone
                    self.tested_at = timezone.now()
            except TestItem.DoesNotExist:
                pass
        super().save(*args, **kwargs)


# ==============================================================================
# Admin Guide Models
# ==============================================================================

GUIDE_TYPE_CHOICES = [
    ('admin', 'Admin Guide'),
    ('data_dictionary', 'Data Dictionary'),
    ('user', 'User Guide'),
]


class AdminGuideSection(models.Model):
    """A section in a guide (Admin Guide, Data Dictionary, or User Guide)."""
    guide_type = models.CharField(
        max_length=20,
        choices=GUIDE_TYPE_CHOICES,
        default='admin',
        db_index=True,
        help_text="Which guide this section belongs to"
    )
    section_key = models.SlugField(
        max_length=100,
        help_text="Unique identifier for this section within its guide"
    )
    title = models.CharField(max_length=200)
    icon = models.CharField(
        max_length=10,
        default="📄",
        help_text="Emoji icon for sidebar display"
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description shown below the section title"
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']
        unique_together = [('guide_type', 'section_key')]
        verbose_name = 'Admin Guide Section'
        verbose_name_plural = 'Admin Guide Sections'

    def __str__(self):
        return f"{self.icon} {self.title}"


class AdminGuideArticle(models.Model):
    """An article within a guide section. Content is Markdown."""
    section = models.ForeignKey(
        AdminGuideSection,
        on_delete=models.CASCADE,
        related_name='articles'
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    content = models.TextField(
        help_text="Article content in Markdown format"
    )
    order = models.PositiveIntegerField(default=0)
    is_editable = models.BooleanField(
        default=False,
        help_text="If True, admin can edit via web interface"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']
        unique_together = [('section', 'slug')]
        verbose_name = 'Admin Guide Article'
        verbose_name_plural = 'Admin Guide Articles'

    def __str__(self):
        return f"{self.section.title} > {self.title}"


# =============================================================================
# UI TEST RUN MODELS
# =============================================================================

class UITestRun(models.Model):
    """
    Record of a WLJ UI test framework run (wlj_ui_tests).

    Separate from core.TestRun which tracks Django unit tests.
    Stores per-run results for the Playwright-based UI test suite.
    """

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('passed', 'All Passed'),
        ('failed', 'Some Failed'),
        ('error', 'Error'),
    ]

    # Run metadata
    run_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='running')
    modules = models.JSONField(
        default=list,
        help_text="List of module names tested (e.g. ['journal', 'smoke'])"
    )

    # Results
    total_cases = models.PositiveIntegerField(default=0)
    passed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    pass_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Pass rate as percentage"
    )
    duration_seconds = models.FloatField(default=0, help_text="Total run time in seconds")

    # Framework run ID (from ExecutionOrchestrator)
    run_id = models.CharField(max_length=50, blank=True, help_text="WLJ UI framework RUN_ID")

    # Raw output
    output = models.TextField(blank=True, help_text="Combined stdout/stderr from run")

    # Full-suite parent-child linking
    parent_run = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE,
        related_name='child_runs',
        help_text="Parent full-suite run (null for standalone or parent runs)"
    )

    # Environment tracking (for centralized local→production reporting)
    ENVIRONMENT_CHOICES = [
        ('local', 'Local'),
        ('production', 'Production'),
        ('ci', 'CI'),
    ]
    environment = models.CharField(
        max_length=20, default='local', choices=ENVIRONMENT_CHOICES,
        help_text="Environment where tests ran"
    )
    source_host = models.CharField(
        max_length=255, blank=True,
        help_text="Hostname of machine that ran the tests"
    )
    source_user = models.CharField(
        max_length=255, blank=True,
        help_text="OS username or identifier of who triggered the run"
    )
    case_results = models.JSONField(
        default=dict, blank=True,
        help_text='Per-test-case results: {"passed": [...], "failed": [...]}'
    )

    class Meta:
        ordering = ['-run_at']
        verbose_name = "UI Test Run"
        verbose_name_plural = "UI Test Runs"

    def __str__(self):
        module_str = ", ".join(self.modules) if self.modules else "none"
        return f"UI Test Run {self.run_at.strftime('%Y-%m-%d %H:%M')} [{module_str}] - {self.status}"

    @property
    def modules_display(self):
        """Return modules as a comma-separated display string."""
        return ", ".join(self.modules) if self.modules else "None"

    @property
    def is_full_suite(self):
        """True if this is a full-suite parent run."""
        return 'full_suite' in self.modules


# ==============================================================================
# Beth Acceptance Center — persisted live quality-validation runs
# (Admin Console → AI Operations → Beth Acceptance Center)
# ==============================================================================
from django.conf import settings as _dj_settings


class AcceptanceRun(models.Model):
    """One execution of the Beth acceptance suite against the live chat stack."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),       # the run itself errored (not a question failure)
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        _dj_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="beth_acceptance_runs_created")
    target_user = models.ForeignKey(
        _dj_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="beth_acceptance_runs_targeted")

    suite_name = models.CharField(max_length=32, default="full")
    depth = models.CharField(max_length=16, default="full")     # smoke/full/deep
    environment = models.CharField(max_length=40, blank=True)
    git_commit = models.CharField(max_length=40, blank=True)

    total_count = models.PositiveIntegerField(default=0)
    pass_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    score_percent = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)

    # Release readiness + failure analytics
    grade = models.CharField(max_length=8, blank=True)          # GREEN/YELLOW/RED
    critical_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    avg_response_ms = models.PositiveIntegerField(default=0)
    category_summary = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="running")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    chatgpt_review_prompt = models.TextField(blank=True)
    claude_fix_prompt = models.TextField(blank=True)
    raw_report_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]),
                   models.Index(fields=["status"])]

    def __str__(self):
        return f"AcceptanceRun #{self.pk} {self.suite_name} {self.score_percent}%"

    @property
    def is_running(self):
        return self.status == "running"

    @property
    def is_green(self):
        return self.status == "completed" and self.fail_count == 0

    @property
    def status_color(self):
        if self.status == "running":
            return "#6b7280"
        if self.status == "failed":
            return "#ef4444"
        if self.fail_count == 0:
            return "#10b981"
        if self.score_percent >= 70:
            return "#f59e0b"
        return "#ef4444"

    @property
    def grade_color(self):
        return {"GREEN": "#10b981", "YELLOW": "#f59e0b",
                "RED": "#ef4444"}.get(self.grade, self.status_color)


class AcceptanceResult(models.Model):
    """One question's evaluated response within an AcceptanceRun."""

    run = models.ForeignKey(AcceptanceRun, on_delete=models.CASCADE,
                            related_name="results")
    question_key = models.CharField(max_length=64)
    suite = models.CharField(max_length=32, blank=True)
    question_text = models.TextField(blank=True)

    expected_intent = models.CharField(max_length=64, blank=True)
    expected_lane = models.CharField(max_length=64, blank=True)
    actual_intent = models.CharField(max_length=64, blank=True)
    actual_lane = models.CharField(max_length=64, blank=True)

    response_text = models.TextField(blank=True)
    response_time_ms = models.PositiveIntegerField(default=0)

    passed = models.BooleanField(default=False)
    failed_rules = models.JSONField(default=list, blank=True)
    required_concepts = models.JSONField(default=list, blank=True)
    forbidden_concepts = models.JSONField(default=list, blank=True)

    openai_called = models.BooleanField(default=False)
    fallback_used = models.BooleanField(null=True, blank=True)
    raw_result_json = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    is_critical = models.BooleanField(default=False)    # release-blocking failure
    is_slow = models.BooleanField(default=False)        # response-time warning

    class Meta:
        ordering = ["run", "sort_order"]

    def __str__(self):
        return f"{self.question_key} {'PASS' if self.passed else 'FAIL'}"
