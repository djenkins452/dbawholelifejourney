"""
ISE — Scheduler Models.

ScheduledIntelligenceTask: Tracks scheduled engine execution state.
SchedulerLock: Database-backed singleton lock for scheduler dedup.
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


class SchedulerLock(models.Model):
    """
    Database-backed singleton lock for scheduler deduplication.

    Prevents duplicate APScheduler instances across Gunicorn workers,
    container restarts, or multi-instance deployments.
    """

    lock_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Lock identifier (e.g., 'apscheduler_main').",
    )
    locked_at = models.DateTimeField(
        help_text="When the lock was acquired or last refreshed.",
    )
    locked_by = models.CharField(
        max_length=255,
        help_text="Hostname-PID of the process holding the lock.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_scheduler_lock"
        verbose_name = "Scheduler Lock"
        verbose_name_plural = "Scheduler Locks"

    def __str__(self):
        return f"{self.lock_name} (by {self.locked_by} at {self.locked_at})"


class EngineRunToken(models.Model):
    """
    Phase 6: DB-backed run token for scheduler overlap protection.

    Guarantees exactly-once execution per engine+user+window even when
    Redis is unavailable. A token is acquired at the start of a scheduler
    run and released on completion. Stale tokens (past expires_at) are
    safe to reclaim.

    Cleanup strategy: tokens older than 24 hours are eligible for bulk
    deletion by a periodic cleanup task or at the start of each scheduler
    cycle.
    """

    engine_name = models.CharField(
        max_length=30,
        help_text="Engine or task name (e.g., 'run_protective_sweep').",
    )
    user_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="User ID if this is a per-user engine run. Null for global tasks.",
    )
    window_key = models.CharField(
        max_length=100,
        help_text="Time-window key for dedup (e.g., '2026-02-23T14:00').",
    )
    acquired_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this token was acquired.",
    )
    expires_at = models.DateTimeField(
        help_text="Token expiry — stale after this time.",
    )
    acquired_by = models.CharField(
        max_length=255,
        help_text="Hostname-PID of the process that acquired this token.",
    )
    completed = models.BooleanField(
        default=False,
        help_text="Set to True when the run finishes successfully.",
    )

    class Meta:
        app_label = "core"
        db_table = "core_engine_run_token"
        verbose_name = "Engine Run Token"
        verbose_name_plural = "Engine Run Tokens"
        constraints = [
            models.UniqueConstraint(
                fields=["engine_name", "user_id", "window_key"],
                name="unique_engine_run_token",
            ),
        ]
        indexes = [
            models.Index(
                fields=["engine_name", "expires_at"],
                name="idx_run_token_expiry",
            ),
        ]

    def __str__(self):
        status = "completed" if self.completed else "active"
        return (
            f"RunToken {self.engine_name} user={self.user_id} "
            f"window={self.window_key} ({status})"
        )

    @property
    def is_expired(self):
        """Check if this token has expired."""
        return timezone.now() > self.expires_at

    @classmethod
    def acquire(cls, engine_name, window_key, user_id=None,
                lease_seconds=300, acquired_by=''):
        """
        Attempt to acquire a run token. Returns the token if acquired,
        None if another process already holds it.

        If an expired token exists, it is reclaimed.
        """
        import os
        import socket

        from django.db import IntegrityError, transaction

        now = timezone.now()
        expires_at = now + timezone.timedelta(seconds=lease_seconds)
        if not acquired_by:
            acquired_by = f"{socket.gethostname()}-{os.getpid()}"

        try:
            with transaction.atomic():
                # Try to reclaim expired token
                reclaimed = cls.objects.filter(
                    engine_name=engine_name,
                    user_id=user_id,
                    window_key=window_key,
                    expires_at__lt=now,
                ).update(
                    acquired_at=now,
                    expires_at=expires_at,
                    acquired_by=acquired_by,
                    completed=False,
                )
                if reclaimed:
                    return cls.objects.get(
                        engine_name=engine_name,
                        user_id=user_id,
                        window_key=window_key,
                    )

                # Check if a valid (non-expired) token already exists.
                # Needed because SQL UniqueConstraint does not treat
                # NULL=NULL as duplicate (user_id can be NULL).
                if cls.objects.filter(
                    engine_name=engine_name,
                    user_id=user_id,
                    window_key=window_key,
                    expires_at__gte=now,
                ).exists():
                    return None

                # Try to create new token
                return cls.objects.create(
                    engine_name=engine_name,
                    user_id=user_id,
                    window_key=window_key,
                    acquired_at=now,
                    expires_at=expires_at,
                    acquired_by=acquired_by,
                )
        except IntegrityError:
            # Another process already holds a valid token
            return None

    @classmethod
    def release(cls, engine_name, window_key, user_id=None, mark_completed=True):
        """Release a run token, optionally marking it completed."""
        cls.objects.filter(
            engine_name=engine_name,
            user_id=user_id,
            window_key=window_key,
        ).update(completed=mark_completed)

    @classmethod
    def cleanup_expired(cls, max_age_hours=24):
        """Delete tokens older than max_age_hours. Called periodically."""
        cutoff = timezone.now() - timezone.timedelta(hours=max_age_hours)
        deleted, _ = cls.objects.filter(acquired_at__lt=cutoff).delete()
        return deleted
