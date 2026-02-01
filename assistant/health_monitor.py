"""
System Health Monitor for Personal Assistant Self-Improvement System.

Owner: admin@wholelifejourney.com

This module provides health monitoring services that track system health
and pause improvements if issues are detected. It protects the system
from cascading failures by monitoring:
- Error rates for improvement tasks
- Rollback rates indicating problems
- Overall system responsiveness

Documentation: See docs/assistant/SELF_IMPROVEMENT.md#safety-limits
Runbook: See docs/assistant/RUNBOOK.md#system-auto-paused-due-to-error-rate
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Optional, Dict, Any

from django.core.cache import cache
from django.utils import timezone

from .models import ImprovementTaskModel
from .notifications import AdminNotificationService, TaskInfo
from .safety_limits import SafetyLimitService


# Configure logging
logger = logging.getLogger(__name__)


# ==============================================================================
# HEALTH MONITOR CONSTANTS
# ==============================================================================

# Error rate thresholds (percentage of failed tasks)
ERROR_RATE_DEGRADED_THRESHOLD = 20  # 20% error rate = DEGRADED
ERROR_RATE_CRITICAL_THRESHOLD = 40  # 40% error rate = CRITICAL

# Rollback rate thresholds (percentage of completed tasks that were rolled back)
ROLLBACK_RATE_DEGRADED_THRESHOLD = 15  # 15% rollback rate = DEGRADED
ROLLBACK_RATE_CRITICAL_THRESHOLD = 30  # 30% rollback rate = CRITICAL

# Time windows for rate calculations
RATE_CALCULATION_HOURS = 24  # Look at last 24 hours for rate calculations
RECENT_TASK_SAMPLE_SIZE = 20  # Number of recent tasks to analyze

# Consecutive failure threshold
CONSECUTIVE_FAILURE_THRESHOLD = 5  # 5 consecutive failures = CRITICAL

# Health check interval (in minutes)
HEALTH_CHECK_INTERVAL_MINUTES = 15

# Cache keys
CACHE_KEY_LAST_HEALTH_CHECK = 'health_monitor:last_check'
CACHE_KEY_HEALTH_STATUS = 'health_monitor:status'
CACHE_KEY_CONSECUTIVE_FAILURES = 'health_monitor:consecutive_failures'


# ==============================================================================
# ENUMS AND DATA CLASSES
# ==============================================================================

class SystemStatus(Enum):
    """System health status levels."""
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    CRITICAL = 'critical'


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    status: SystemStatus
    reason: str
    error_rate: float = 0.0
    rollback_rate: float = 0.0
    consecutive_failures: int = 0
    details: Optional[Dict[str, Any]] = None


@dataclass
class RateMetrics:
    """Metrics for rate calculations."""
    total_count: int
    error_count: int
    rollback_count: int
    completed_count: int
    error_rate: float
    rollback_rate: float
    consecutive_failures: int


# ==============================================================================
# HEALTH MONITOR SERVICE
# ==============================================================================

class HealthMonitor:
    """
    Service for monitoring system health and detecting problems.

    Monitors:
    - Error rate: Percentage of tasks that failed
    - Rollback rate: Percentage of completed tasks that were rolled back
    - Consecutive failures: Number of failures in a row

    Actions based on status:
    - HEALTHY: Normal operation, all improvements allowed
    - DEGRADED: Pause autonomous improvements, allow approved only
    - CRITICAL: Pause ALL improvements, require admin intervention
    """

    def __init__(
        self,
        notification_service: Optional[AdminNotificationService] = None,
        safety_limit_service: Optional[SafetyLimitService] = None
    ):
        """
        Initialize the health monitor.

        Args:
            notification_service: Service for sending admin notifications.
            safety_limit_service: Service for pausing/resuming the system.
        """
        self.notification_service = notification_service or AdminNotificationService()
        self.safety_limit_service = safety_limit_service or SafetyLimitService(
            notification_service=self.notification_service
        )

    # --------------------------------------------------------------------------
    # Rate Calculation Methods
    # --------------------------------------------------------------------------

    def _get_rate_metrics(self) -> RateMetrics:
        """
        Calculate current rate metrics from recent tasks.

        Returns:
            RateMetrics with current error and rollback rates.
        """
        now = timezone.now()
        time_window = now - timedelta(hours=RATE_CALCULATION_HOURS)

        # Get recent tasks
        recent_tasks = ImprovementTaskModel.objects.filter(
            updated_at__gte=time_window
        ).order_by('-updated_at')

        total_count = recent_tasks.count()

        if total_count == 0:
            return RateMetrics(
                total_count=0,
                error_count=0,
                rollback_count=0,
                completed_count=0,
                error_rate=0.0,
                rollback_rate=0.0,
                consecutive_failures=0
            )

        # Count by status
        error_count = recent_tasks.filter(
            status=ImprovementTaskModel.STATUS_ERROR
        ).count()

        rollback_count = recent_tasks.filter(
            status=ImprovementTaskModel.STATUS_ROLLED_BACK
        ).count()

        completed_count = recent_tasks.filter(
            status=ImprovementTaskModel.STATUS_COMPLETED
        ).count()

        # Calculate rates
        error_rate = (error_count / total_count) * 100 if total_count > 0 else 0.0

        # Rollback rate is relative to completed + rolled back tasks
        completed_plus_rollback = completed_count + rollback_count
        rollback_rate = (rollback_count / completed_plus_rollback) * 100 if completed_plus_rollback > 0 else 0.0

        # Calculate consecutive failures
        consecutive_failures = self._count_consecutive_failures()

        return RateMetrics(
            total_count=total_count,
            error_count=error_count,
            rollback_count=rollback_count,
            completed_count=completed_count,
            error_rate=error_rate,
            rollback_rate=rollback_rate,
            consecutive_failures=consecutive_failures
        )

    def _count_consecutive_failures(self) -> int:
        """
        Count consecutive task failures from most recent tasks.

        Returns:
            Number of consecutive failures.
        """
        # Get most recent tasks ordered by updated_at
        recent_tasks = ImprovementTaskModel.objects.filter(
            status__in=[
                ImprovementTaskModel.STATUS_COMPLETED,
                ImprovementTaskModel.STATUS_ERROR,
                ImprovementTaskModel.STATUS_ROLLED_BACK,
            ]
        ).order_by('-updated_at')[:RECENT_TASK_SAMPLE_SIZE]

        consecutive = 0
        for task in recent_tasks:
            if task.status in [
                ImprovementTaskModel.STATUS_ERROR,
                ImprovementTaskModel.STATUS_ROLLED_BACK
            ]:
                consecutive += 1
            else:
                # Break on first success
                break

        return consecutive

    # --------------------------------------------------------------------------
    # Individual Health Checks
    # --------------------------------------------------------------------------

    def check_error_rate(self) -> HealthCheckResult:
        """
        Check the error rate for improvement task failures.

        Returns:
            HealthCheckResult based on error rate.
        """
        metrics = self._get_rate_metrics()

        if metrics.error_rate >= ERROR_RATE_CRITICAL_THRESHOLD:
            return HealthCheckResult(
                status=SystemStatus.CRITICAL,
                reason=f"Critical error rate: {metrics.error_rate:.1f}% "
                       f"({metrics.error_count}/{metrics.total_count} tasks failed)",
                error_rate=metrics.error_rate,
                details={
                    'error_count': metrics.error_count,
                    'total_count': metrics.total_count,
                    'threshold': ERROR_RATE_CRITICAL_THRESHOLD
                }
            )

        if metrics.error_rate >= ERROR_RATE_DEGRADED_THRESHOLD:
            return HealthCheckResult(
                status=SystemStatus.DEGRADED,
                reason=f"Elevated error rate: {metrics.error_rate:.1f}% "
                       f"({metrics.error_count}/{metrics.total_count} tasks failed)",
                error_rate=metrics.error_rate,
                details={
                    'error_count': metrics.error_count,
                    'total_count': metrics.total_count,
                    'threshold': ERROR_RATE_DEGRADED_THRESHOLD
                }
            )

        return HealthCheckResult(
            status=SystemStatus.HEALTHY,
            reason=f"Error rate OK: {metrics.error_rate:.1f}%",
            error_rate=metrics.error_rate
        )

    def check_rollback_rate(self) -> HealthCheckResult:
        """
        Check the rollback rate - high rollbacks indicate problems.

        Returns:
            HealthCheckResult based on rollback rate.
        """
        metrics = self._get_rate_metrics()

        if metrics.rollback_rate >= ROLLBACK_RATE_CRITICAL_THRESHOLD:
            return HealthCheckResult(
                status=SystemStatus.CRITICAL,
                reason=f"Critical rollback rate: {metrics.rollback_rate:.1f}% "
                       f"({metrics.rollback_count} of {metrics.completed_count + metrics.rollback_count} completions rolled back)",
                rollback_rate=metrics.rollback_rate,
                details={
                    'rollback_count': metrics.rollback_count,
                    'completed_count': metrics.completed_count,
                    'threshold': ROLLBACK_RATE_CRITICAL_THRESHOLD
                }
            )

        if metrics.rollback_rate >= ROLLBACK_RATE_DEGRADED_THRESHOLD:
            return HealthCheckResult(
                status=SystemStatus.DEGRADED,
                reason=f"Elevated rollback rate: {metrics.rollback_rate:.1f}% "
                       f"({metrics.rollback_count} of {metrics.completed_count + metrics.rollback_count} completions rolled back)",
                rollback_rate=metrics.rollback_rate,
                details={
                    'rollback_count': metrics.rollback_count,
                    'completed_count': metrics.completed_count,
                    'threshold': ROLLBACK_RATE_DEGRADED_THRESHOLD
                }
            )

        return HealthCheckResult(
            status=SystemStatus.HEALTHY,
            reason=f"Rollback rate OK: {metrics.rollback_rate:.1f}%",
            rollback_rate=metrics.rollback_rate
        )

    def check_assistant_response_rate(self) -> HealthCheckResult:
        """
        Check if the assistant is failing to respond/execute tasks.

        Detects issues like:
        - Multiple consecutive failures
        - Tasks stuck in IN_PROGRESS state

        Returns:
            HealthCheckResult based on response patterns.
        """
        metrics = self._get_rate_metrics()

        # Check consecutive failures
        if metrics.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
            return HealthCheckResult(
                status=SystemStatus.CRITICAL,
                reason=f"Critical: {metrics.consecutive_failures} consecutive task failures",
                consecutive_failures=metrics.consecutive_failures,
                details={
                    'consecutive_failures': metrics.consecutive_failures,
                    'threshold': CONSECUTIVE_FAILURE_THRESHOLD
                }
            )

        # Check for stuck tasks (IN_PROGRESS for more than 1 hour)
        stuck_threshold = timezone.now() - timedelta(hours=1)
        stuck_tasks = ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_IN_PROGRESS,
            updated_at__lt=stuck_threshold
        )
        stuck_count = stuck_tasks.count()

        if stuck_count >= 3:
            return HealthCheckResult(
                status=SystemStatus.CRITICAL,
                reason=f"Critical: {stuck_count} tasks stuck in IN_PROGRESS state",
                details={
                    'stuck_count': stuck_count,
                    'stuck_tasks': list(stuck_tasks.values_list('id', flat=True)[:5])
                }
            )

        if stuck_count >= 1:
            return HealthCheckResult(
                status=SystemStatus.DEGRADED,
                reason=f"Warning: {stuck_count} task(s) stuck in IN_PROGRESS state",
                details={
                    'stuck_count': stuck_count,
                    'stuck_tasks': list(stuck_tasks.values_list('id', flat=True))
                }
            )

        # Check if we have any consecutive failures (less than threshold)
        if metrics.consecutive_failures >= 3:
            return HealthCheckResult(
                status=SystemStatus.DEGRADED,
                reason=f"Warning: {metrics.consecutive_failures} consecutive failures",
                consecutive_failures=metrics.consecutive_failures
            )

        return HealthCheckResult(
            status=SystemStatus.HEALTHY,
            reason="Assistant response rate is normal",
            consecutive_failures=metrics.consecutive_failures
        )

    # --------------------------------------------------------------------------
    # Main Health Check Method
    # --------------------------------------------------------------------------

    def get_system_status(self) -> HealthCheckResult:
        """
        Get the overall system health status.

        Combines all health checks and returns the most severe status.
        Status levels:
        - HEALTHY: All checks pass
        - DEGRADED: One or more checks show degraded status
        - CRITICAL: One or more checks show critical status

        Returns:
            HealthCheckResult with overall system status.
        """
        logger.info("Running system health check...")

        # Run all health checks
        checks = [
            ('error_rate', self.check_error_rate()),
            ('rollback_rate', self.check_rollback_rate()),
            ('response_rate', self.check_assistant_response_rate()),
        ]

        # Collect results and find worst status
        worst_status = SystemStatus.HEALTHY
        check_results = {}
        reasons = []

        for name, result in checks:
            check_results[name] = {
                'status': result.status.value,
                'reason': result.reason,
                'details': result.details
            }

            if result.status == SystemStatus.CRITICAL:
                worst_status = SystemStatus.CRITICAL
                reasons.append(f"[CRITICAL] {result.reason}")
            elif result.status == SystemStatus.DEGRADED and worst_status != SystemStatus.CRITICAL:
                worst_status = SystemStatus.DEGRADED
                reasons.append(f"[DEGRADED] {result.reason}")

        # Get metrics for the combined result
        metrics = self._get_rate_metrics()

        # Build combined reason
        if worst_status == SystemStatus.HEALTHY:
            combined_reason = "All health checks passed"
        else:
            combined_reason = "; ".join(reasons)

        # Store the health status in cache
        cache.set(CACHE_KEY_HEALTH_STATUS, worst_status.value, timeout=HEALTH_CHECK_INTERVAL_MINUTES * 60 * 2)
        cache.set(CACHE_KEY_LAST_HEALTH_CHECK, timezone.now().isoformat(), timeout=86400)

        logger.info(f"Health check complete: {worst_status.value} - {combined_reason}")

        return HealthCheckResult(
            status=worst_status,
            reason=combined_reason,
            error_rate=metrics.error_rate,
            rollback_rate=metrics.rollback_rate,
            consecutive_failures=metrics.consecutive_failures,
            details={
                'checks': check_results,
                'metrics': {
                    'total_count': metrics.total_count,
                    'error_count': metrics.error_count,
                    'rollback_count': metrics.rollback_count,
                    'completed_count': metrics.completed_count,
                }
            }
        )

    # --------------------------------------------------------------------------
    # Status Action Methods
    # --------------------------------------------------------------------------

    def handle_status(self, result: HealthCheckResult) -> Dict[str, Any]:
        """
        Take action based on the health check result.

        Actions:
        - HEALTHY: Ensure system is running normally
        - DEGRADED: Pause autonomous improvements, allow approved only
        - CRITICAL: Pause ALL improvements, notify admin urgently

        Args:
            result: The HealthCheckResult to act on.

        Returns:
            Dictionary with actions taken.
        """
        actions_taken = {
            'status': result.status.value,
            'actions': [],
            'notifications_sent': False
        }

        if result.status == SystemStatus.CRITICAL:
            # Pause ALL improvements
            self.safety_limit_service.pause_system(
                reason=f"CRITICAL: System health check failed - {result.reason}"
            )
            actions_taken['actions'].append('Paused all improvements')

            # Notify admin urgently
            self._notify_critical_status(result)
            actions_taken['notifications_sent'] = True
            actions_taken['actions'].append('Sent critical alert to admin')

            logger.critical(f"System health CRITICAL: {result.reason}")

        elif result.status == SystemStatus.DEGRADED:
            # Pause autonomous improvements (approved tasks can still run)
            self.safety_limit_service.pause_system(
                reason=f"DEGRADED: System health degraded - {result.reason}"
            )
            actions_taken['actions'].append('Paused autonomous improvements')

            # Notify admin
            self._notify_degraded_status(result)
            actions_taken['notifications_sent'] = True
            actions_taken['actions'].append('Sent degraded status alert to admin')

            logger.warning(f"System health DEGRADED: {result.reason}")

        else:
            # HEALTHY - ensure system is not paused (unless manually paused)
            # Don't auto-resume to respect manual pauses
            actions_taken['actions'].append('No action needed - system healthy')
            logger.info("System health check passed")

        return actions_taken

    def _notify_critical_status(self, result: HealthCheckResult):
        """
        Send critical status notification to admin.

        Args:
            result: The health check result.
        """
        task_info = TaskInfo(
            task_id=0,
            title="CRITICAL: System Health Alert",
            description=result.reason,
            severity="high"
        )

        try:
            self.notification_service.notify_task_error(
                task=task_info,
                error_details=(
                    f"System health is CRITICAL.\n\n"
                    f"Reason: {result.reason}\n\n"
                    f"Metrics:\n"
                    f"- Error Rate: {result.error_rate:.1f}%\n"
                    f"- Rollback Rate: {result.rollback_rate:.1f}%\n"
                    f"- Consecutive Failures: {result.consecutive_failures}\n\n"
                    f"All autonomous improvements have been PAUSED.\n"
                    f"Manual intervention is required."
                ),
                rollback_successful=False
            )
            logger.info("Critical status notification sent to admin")
        except Exception as e:
            logger.error(f"Failed to send critical notification: {e}")

    def _notify_degraded_status(self, result: HealthCheckResult):
        """
        Send degraded status notification to admin.

        Args:
            result: The health check result.
        """
        queue_status = {
            'limit_name': 'System Health',
            'current_value': result.error_rate,
            'limit_value': ERROR_RATE_DEGRADED_THRESHOLD,
            'reason': result.reason,
            'stuck': 0,
            'health_status': 'DEGRADED',
            'error_rate': result.error_rate,
            'rollback_rate': result.rollback_rate,
        }

        try:
            self.notification_service.notify_queue_status(queue_status)
            logger.info("Degraded status notification sent to admin")
        except Exception as e:
            logger.error(f"Failed to send degraded notification: {e}")

    # --------------------------------------------------------------------------
    # Periodic Health Check
    # --------------------------------------------------------------------------

    def run_periodic_check(self) -> Dict[str, Any]:
        """
        Run a periodic health check and take appropriate actions.

        This method is designed to be called every 15 minutes by
        the background task scheduler.

        Returns:
            Dictionary with check results and actions taken.
        """
        logger.info("Running periodic health check...")

        # Get current status
        result = self.get_system_status()

        # Take appropriate actions
        actions = self.handle_status(result)

        return {
            'timestamp': timezone.now().isoformat(),
            'status': result.status.value,
            'reason': result.reason,
            'error_rate': result.error_rate,
            'rollback_rate': result.rollback_rate,
            'consecutive_failures': result.consecutive_failures,
            'actions': actions
        }

    # --------------------------------------------------------------------------
    # Status Query Methods
    # --------------------------------------------------------------------------

    def get_cached_status(self) -> Optional[str]:
        """
        Get the cached health status without running a new check.

        Returns:
            Cached status string or None if no cached status.
        """
        return cache.get(CACHE_KEY_HEALTH_STATUS)

    def get_last_check_time(self) -> Optional[str]:
        """
        Get the timestamp of the last health check.

        Returns:
            ISO timestamp string or None if no check has run.
        """
        return cache.get(CACHE_KEY_LAST_HEALTH_CHECK)

    def get_full_status_report(self) -> Dict[str, Any]:
        """
        Get a full status report including metrics and recommendations.

        Returns:
            Dictionary with comprehensive status information.
        """
        result = self.get_system_status()
        metrics = self._get_rate_metrics()

        # Generate recommendations based on status
        recommendations = []
        if result.status == SystemStatus.CRITICAL:
            recommendations.extend([
                "Review recent task failures for common causes",
                "Check application logs for errors",
                "Consider reverting recent code changes",
                "Manually inspect and fix any stuck tasks"
            ])
        elif result.status == SystemStatus.DEGRADED:
            recommendations.extend([
                "Monitor the system closely",
                "Review recent task errors",
                "Consider pausing new task creation"
            ])

        return {
            'status': result.status.value,
            'status_display': result.status.value.upper(),
            'reason': result.reason,
            'last_check': self.get_last_check_time(),
            'metrics': {
                'error_rate': round(metrics.error_rate, 1),
                'rollback_rate': round(metrics.rollback_rate, 1),
                'consecutive_failures': metrics.consecutive_failures,
                'total_tasks_24h': metrics.total_count,
                'errors_24h': metrics.error_count,
                'rollbacks_24h': metrics.rollback_count,
                'completed_24h': metrics.completed_count,
            },
            'thresholds': {
                'error_rate_degraded': ERROR_RATE_DEGRADED_THRESHOLD,
                'error_rate_critical': ERROR_RATE_CRITICAL_THRESHOLD,
                'rollback_rate_degraded': ROLLBACK_RATE_DEGRADED_THRESHOLD,
                'rollback_rate_critical': ROLLBACK_RATE_CRITICAL_THRESHOLD,
                'consecutive_failure_critical': CONSECUTIVE_FAILURE_THRESHOLD,
            },
            'recommendations': recommendations,
            'details': result.details
        }


# ==============================================================================
# PERIODIC TASK FUNCTION
# ==============================================================================

def run_health_check() -> Dict[str, Any]:
    """
    Run the periodic health check.

    This function is designed to be called by APScheduler every 15 minutes.

    Returns:
        Dictionary with health check results.
    """
    monitor = HealthMonitor()
    return monitor.run_periodic_check()


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def get_system_status() -> HealthCheckResult:
    """
    Convenience function to get current system status.

    Returns:
        HealthCheckResult with current status.
    """
    monitor = HealthMonitor()
    return monitor.get_system_status()


def get_status_report() -> Dict[str, Any]:
    """
    Convenience function to get a full status report.

    Returns:
        Dictionary with comprehensive status information.
    """
    monitor = HealthMonitor()
    return monitor.get_full_status_report()
