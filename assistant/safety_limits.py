"""
Safety Limits for Personal Assistant Self-Improvement System.

Owner: admin@wholelifejourney.com

This module provides rate limiting and safety caps to prevent runaway
self-modification by the autonomous executor system. All limits can be
overridden by admins through the SafetyLimitOverride model.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple

from django.core.cache import cache
from django.db import models
from django.utils import timezone

from .notifications import AdminNotificationService, TaskInfo


# Configure logging
logger = logging.getLogger(__name__)


# ==============================================================================
# SAFETY LIMIT CONSTANTS
# ==============================================================================

# Maximum autonomous task executions per hour
MAX_AUTONOMOUS_PER_HOUR = 5

# Maximum autonomous task executions per day
MAX_AUTONOMOUS_PER_DAY = 20

# Maximum pending tasks allowed in queue before pausing
MAX_PENDING_TASKS = 50

# Maximum modifications per file per day
MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY = 3

# Error rate threshold (percentage) - pause if exceeded
ERROR_RATE_THRESHOLD = 30

# Number of recent tasks to check for error rate
ERROR_RATE_SAMPLE_SIZE = 10

# Cache keys for rate limiting
CACHE_KEY_HOURLY_COUNT = 'safety_limits:autonomous_hourly_count'
CACHE_KEY_DAILY_COUNT = 'safety_limits:autonomous_daily_count'
CACHE_KEY_FILE_MODIFICATIONS = 'safety_limits:file_modifications:{file_path}'
CACHE_KEY_SYSTEM_PAUSED = 'safety_limits:system_paused'


# ==============================================================================
# SAFETY LIMIT OVERRIDE MODEL
# ==============================================================================

class SafetyLimitOverride(models.Model):
    """
    Model to store admin overrides for safety limits.

    Allows admins to temporarily or permanently adjust safety limits
    without code changes.
    """

    LIMIT_CHOICES = [
        ('max_autonomous_per_hour', 'Max Autonomous Per Hour'),
        ('max_autonomous_per_day', 'Max Autonomous Per Day'),
        ('max_pending_tasks', 'Max Pending Tasks'),
        ('max_file_modifications_per_day', 'Max File Modifications Per Day'),
        ('error_rate_threshold', 'Error Rate Threshold'),
        ('system_enabled', 'System Enabled'),
    ]

    limit_name = models.CharField(
        max_length=50,
        choices=LIMIT_CHOICES,
        unique=True,
        help_text='The safety limit to override'
    )

    value = models.IntegerField(
        help_text='Override value for the limit'
    )

    is_active = models.BooleanField(
        default=True,
        help_text='Whether this override is currently active'
    )

    reason = models.TextField(
        blank=True,
        help_text='Reason for the override'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this override expires (null = never)'
    )

    class Meta:
        app_label = 'assistant'
        verbose_name = 'Safety Limit Override'
        verbose_name_plural = 'Safety Limit Overrides'

    def __str__(self):
        return f"{self.get_limit_name_display()}: {self.value}"

    def is_valid(self) -> bool:
        """Check if this override is currently valid."""
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    reason: str
    current_count: int = 0
    limit: int = 0


@dataclass
class SystemHealthResult:
    """Result of a system health check."""
    healthy: bool
    reason: str
    error_rate: float = 0.0
    recent_errors: int = 0
    recent_total: int = 0


# ==============================================================================
# SAFETY LIMIT SERVICE
# ==============================================================================

class SafetyLimitService:
    """
    Service for checking and enforcing safety limits on autonomous execution.

    Provides methods to:
    - Check rate limits (hourly/daily)
    - Check file modification limits
    - Check system health (error rate)
    - Notify admin when limits are reached
    - Support admin overrides
    """

    def __init__(self, notification_service: Optional[AdminNotificationService] = None):
        """
        Initialize the safety limit service.

        Args:
            notification_service: Service for sending admin notifications.
        """
        self.notification_service = notification_service or AdminNotificationService()

    # --------------------------------------------------------------------------
    # Override Management
    # --------------------------------------------------------------------------

    def get_limit_value(self, limit_name: str, default: int) -> int:
        """
        Get the effective value for a limit, considering overrides.

        Args:
            limit_name: Name of the limit to check.
            default: Default value if no override exists.

        Returns:
            The effective limit value.
        """
        try:
            override = SafetyLimitOverride.objects.filter(
                limit_name=limit_name,
                is_active=True
            ).first()

            if override and override.is_valid():
                logger.info(f"Using override for {limit_name}: {override.value}")
                return override.value
        except Exception as e:
            # Handle case where table doesn't exist yet
            logger.debug(f"Could not check override for {limit_name}: {e}")

        return default

    def is_system_enabled(self) -> bool:
        """
        Check if the autonomous execution system is enabled.

        Returns:
            True if system is enabled, False if disabled by override.
        """
        # Check cache first for pause state
        if cache.get(CACHE_KEY_SYSTEM_PAUSED):
            return False

        # Check for system_enabled override (1 = enabled, 0 = disabled)
        enabled_value = self.get_limit_value('system_enabled', 1)
        return enabled_value == 1

    def pause_system(self, reason: str = 'Safety limit triggered'):
        """
        Pause the autonomous execution system.

        Args:
            reason: Reason for pausing.
        """
        # Set pause flag in cache (expires in 24 hours by default)
        cache.set(CACHE_KEY_SYSTEM_PAUSED, reason, timeout=86400)
        logger.warning(f"Autonomous execution system paused: {reason}")

        # Notify admin
        self._notify_limit_reached(
            limit_name='System Paused',
            current_value=0,
            limit_value=0,
            reason=reason
        )

    def resume_system(self):
        """Resume the autonomous execution system."""
        cache.delete(CACHE_KEY_SYSTEM_PAUSED)
        logger.info("Autonomous execution system resumed")

    # --------------------------------------------------------------------------
    # Rate Limit Checks
    # --------------------------------------------------------------------------

    def check_rate_limits(self) -> RateLimitResult:
        """
        Check if execution is allowed based on hourly and daily rate limits.

        Queries recent ImprovementTaskModel executions to determine if limits
        have been exceeded.

        Returns:
            RateLimitResult indicating if execution is allowed.
        """
        from .models import ImprovementTaskModel

        # Check if system is enabled
        if not self.is_system_enabled():
            pause_reason = cache.get(CACHE_KEY_SYSTEM_PAUSED, 'Disabled by admin')
            return RateLimitResult(
                allowed=False,
                reason=f"System is paused: {pause_reason}",
                current_count=0,
                limit=0
            )

        now = timezone.now()

        # Get effective limits (considering overrides)
        hourly_limit = self.get_limit_value('max_autonomous_per_hour', MAX_AUTONOMOUS_PER_HOUR)
        daily_limit = self.get_limit_value('max_autonomous_per_day', MAX_AUTONOMOUS_PER_DAY)

        # Check hourly limit
        hour_ago = now - timedelta(hours=1)
        hourly_count = ImprovementTaskModel.objects.filter(
            requires_approval=False,
            status__in=[
                ImprovementTaskModel.STATUS_COMPLETED,
                ImprovementTaskModel.STATUS_ERROR,
                ImprovementTaskModel.STATUS_IN_PROGRESS,
                ImprovementTaskModel.STATUS_TESTING,
            ],
            updated_at__gte=hour_ago
        ).count()

        if hourly_count >= hourly_limit:
            self._notify_limit_reached(
                limit_name='Hourly Rate Limit',
                current_value=hourly_count,
                limit_value=hourly_limit,
                reason='Maximum autonomous executions per hour reached'
            )
            return RateLimitResult(
                allowed=False,
                reason=f"Hourly rate limit exceeded: {hourly_count}/{hourly_limit}",
                current_count=hourly_count,
                limit=hourly_limit
            )

        # Check daily limit
        day_ago = now - timedelta(days=1)
        daily_count = ImprovementTaskModel.objects.filter(
            requires_approval=False,
            status__in=[
                ImprovementTaskModel.STATUS_COMPLETED,
                ImprovementTaskModel.STATUS_ERROR,
                ImprovementTaskModel.STATUS_IN_PROGRESS,
                ImprovementTaskModel.STATUS_TESTING,
            ],
            updated_at__gte=day_ago
        ).count()

        if daily_count >= daily_limit:
            self._notify_limit_reached(
                limit_name='Daily Rate Limit',
                current_value=daily_count,
                limit_value=daily_limit,
                reason='Maximum autonomous executions per day reached'
            )
            return RateLimitResult(
                allowed=False,
                reason=f"Daily rate limit exceeded: {daily_count}/{daily_limit}",
                current_count=daily_count,
                limit=daily_limit
            )

        # Check pending tasks limit
        pending_limit = self.get_limit_value('max_pending_tasks', MAX_PENDING_TASKS)
        pending_count = ImprovementTaskModel.objects.filter(
            status__in=[
                ImprovementTaskModel.STATUS_NEW,
                ImprovementTaskModel.STATUS_PENDING_APPROVAL,
                ImprovementTaskModel.STATUS_APPROVED,
            ]
        ).count()

        if pending_count >= pending_limit:
            self._notify_limit_reached(
                limit_name='Pending Tasks Limit',
                current_value=pending_count,
                limit_value=pending_limit,
                reason='Too many pending tasks in queue'
            )
            return RateLimitResult(
                allowed=False,
                reason=f"Pending tasks limit exceeded: {pending_count}/{pending_limit}",
                current_count=pending_count,
                limit=pending_limit
            )

        logger.debug(
            f"Rate limits OK - Hourly: {hourly_count}/{hourly_limit}, "
            f"Daily: {daily_count}/{daily_limit}, Pending: {pending_count}/{pending_limit}"
        )

        return RateLimitResult(
            allowed=True,
            reason="Within rate limits",
            current_count=hourly_count,
            limit=hourly_limit
        )

    def check_file_modification_limit(self, file_path: str) -> RateLimitResult:
        """
        Check if a specific file can be modified based on daily limits.

        Args:
            file_path: Path to the file to check.

        Returns:
            RateLimitResult indicating if modification is allowed.
        """
        # Get effective limit
        file_limit = self.get_limit_value(
            'max_file_modifications_per_day',
            MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY
        )

        # Normalize file path for cache key
        normalized_path = file_path.replace('/', '_').replace('\\', '_')
        cache_key = CACHE_KEY_FILE_MODIFICATIONS.format(file_path=normalized_path)

        # Get current count from cache
        current_count = cache.get(cache_key, 0)

        if current_count >= file_limit:
            self._notify_limit_reached(
                limit_name='File Modification Limit',
                current_value=current_count,
                limit_value=file_limit,
                reason=f'Maximum daily modifications reached for file: {file_path}'
            )
            return RateLimitResult(
                allowed=False,
                reason=f"File modification limit exceeded for {file_path}: {current_count}/{file_limit}",
                current_count=current_count,
                limit=file_limit
            )

        logger.debug(f"File modification limit OK for {file_path}: {current_count}/{file_limit}")

        return RateLimitResult(
            allowed=True,
            reason=f"File modification allowed: {current_count}/{file_limit}",
            current_count=current_count,
            limit=file_limit
        )

    def record_file_modification(self, file_path: str):
        """
        Record that a file was modified (increment counter).

        Args:
            file_path: Path to the modified file.
        """
        normalized_path = file_path.replace('/', '_').replace('\\', '_')
        cache_key = CACHE_KEY_FILE_MODIFICATIONS.format(file_path=normalized_path)

        current_count = cache.get(cache_key, 0)

        # Set with 24-hour expiry
        cache.set(cache_key, current_count + 1, timeout=86400)

        logger.debug(f"Recorded modification for {file_path}: {current_count + 1}")

    # --------------------------------------------------------------------------
    # System Health Check
    # --------------------------------------------------------------------------

    def is_system_healthy(self) -> SystemHealthResult:
        """
        Check system health by analyzing error rate in recent tasks.

        If error rate exceeds threshold in last N tasks, recommends
        pausing autonomous execution.

        Returns:
            SystemHealthResult with health status and metrics.
        """
        from .models import ImprovementTaskModel

        # Get effective threshold
        error_threshold = self.get_limit_value('error_rate_threshold', ERROR_RATE_THRESHOLD)

        # Get recent tasks (completed or errored)
        recent_tasks = ImprovementTaskModel.objects.filter(
            status__in=[
                ImprovementTaskModel.STATUS_COMPLETED,
                ImprovementTaskModel.STATUS_ERROR,
            ]
        ).order_by('-updated_at')[:ERROR_RATE_SAMPLE_SIZE]

        total_count = recent_tasks.count()

        if total_count == 0:
            return SystemHealthResult(
                healthy=True,
                reason="No recent tasks to analyze",
                error_rate=0.0,
                recent_errors=0,
                recent_total=0
            )

        # Count errors
        error_count = sum(
            1 for task in recent_tasks
            if task.status == ImprovementTaskModel.STATUS_ERROR
        )

        error_rate = (error_count / total_count) * 100

        if error_rate > error_threshold:
            reason = (
                f"Error rate ({error_rate:.1f}%) exceeds threshold ({error_threshold}%). "
                f"{error_count} errors in last {total_count} tasks."
            )

            # Auto-pause the system
            self.pause_system(reason)

            return SystemHealthResult(
                healthy=False,
                reason=reason,
                error_rate=error_rate,
                recent_errors=error_count,
                recent_total=total_count
            )

        logger.debug(
            f"System health OK - Error rate: {error_rate:.1f}% "
            f"({error_count}/{total_count} tasks)"
        )

        return SystemHealthResult(
            healthy=True,
            reason=f"Error rate ({error_rate:.1f}%) is within threshold ({error_threshold}%)",
            error_rate=error_rate,
            recent_errors=error_count,
            recent_total=total_count
        )

    # --------------------------------------------------------------------------
    # Combined Safety Check
    # --------------------------------------------------------------------------

    def check_all_limits(self, file_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Perform all safety checks before autonomous execution.

        Args:
            file_path: Optional file path to check modification limits for.

        Returns:
            Tuple of (is_allowed, reason)
        """
        # Check system health first
        health_result = self.is_system_healthy()
        if not health_result.healthy:
            return (False, health_result.reason)

        # Check rate limits
        rate_result = self.check_rate_limits()
        if not rate_result.allowed:
            return (False, rate_result.reason)

        # Check file modification limit if path provided
        if file_path:
            file_result = self.check_file_modification_limit(file_path)
            if not file_result.allowed:
                return (False, file_result.reason)

        return (True, "All safety checks passed")

    # --------------------------------------------------------------------------
    # Admin Notifications
    # --------------------------------------------------------------------------

    def _notify_limit_reached(
        self,
        limit_name: str,
        current_value: int,
        limit_value: int,
        reason: str
    ):
        """
        Send notification to admin when a limit is reached.

        Args:
            limit_name: Name of the limit that was reached.
            current_value: Current count/value.
            limit_value: The limit threshold.
            reason: Human-readable reason.
        """
        logger.warning(f"Safety limit reached: {limit_name} ({current_value}/{limit_value})")

        # Create a task info for notification
        task_info = TaskInfo(
            task_id=0,
            title=f"Safety Limit Reached: {limit_name}",
            description=reason,
            severity="high"
        )

        # Use queue status notification as it's most appropriate
        queue_status = {
            'limit_name': limit_name,
            'current_value': current_value,
            'limit_value': limit_value,
            'reason': reason,
            'stuck': 1,  # Trigger action required
        }

        try:
            self.notification_service.notify_queue_status(queue_status)
        except Exception as e:
            logger.error(f"Failed to send limit notification: {e}")


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def check_rate_limits() -> RateLimitResult:
    """
    Convenience function to check rate limits.

    Returns:
        RateLimitResult indicating if execution is allowed.
    """
    service = SafetyLimitService()
    return service.check_rate_limits()


def check_file_modification_limit(file_path: str) -> RateLimitResult:
    """
    Convenience function to check file modification limits.

    Args:
        file_path: Path to the file to check.

    Returns:
        RateLimitResult indicating if modification is allowed.
    """
    service = SafetyLimitService()
    return service.check_file_modification_limit(file_path)


def is_system_healthy() -> SystemHealthResult:
    """
    Convenience function to check system health.

    Returns:
        SystemHealthResult with health status.
    """
    service = SafetyLimitService()
    return service.is_system_healthy()
