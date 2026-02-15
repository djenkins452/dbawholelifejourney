"""
ISE — Scheduler Models.

ScheduledIntelligenceTask: Tracks scheduled engine execution state.
"""

from django.db import models
from django.utils import timezone


class ScheduledIntelligenceTask(models.Model):
    """
    Tracks a scheduled intelligence engine task.

    Each record represents one recurring task (e.g., daily briefings,
    guidance refresh). The scheduler checks next_run_at to decide
    whether to execute.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    task_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique identifier matching a registered task.",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable description of what this task does.",
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this task last executed.",
    )
    next_run_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this task should next execute.",
    )
    run_interval_seconds = models.IntegerField(
        default=86400,
        help_text="Seconds between runs.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this task is enabled.",
    )
    last_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Status of the most recent run.",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="Error message from the most recent failed run.",
    )
    run_count = models.IntegerField(
        default=0,
        help_text="Total number of successful runs.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        db_table = "core_scheduled_intelligence_task"
        ordering = ["task_name"]
        verbose_name = "Scheduled Intelligence Task"
        verbose_name_plural = "Scheduled Intelligence Tasks"

    def __str__(self):
        return f"{self.task_name} ({self.last_status}, interval={self.run_interval_seconds}s)"

    @property
    def is_due(self):
        """Check if this task is due for execution."""
        return self.is_active and timezone.now() >= self.next_run_at
