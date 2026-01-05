"""
Background Task Functions for Assistant Improvement Execution.

Owner: admin@wholelifejourney.com

This module provides async task definitions for executing improvement tasks
in the background without blocking user requests.

Tasks are scheduled and run via django-apscheduler using the
run_improvement_scheduler management command.
"""

import logging
import signal
from contextlib import contextmanager
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .executor import AutonomousExecutor, ImprovementExecutor
from .health_monitor import HealthMonitor, run_health_check as _run_health_check
from .models import ImprovementTaskModel
from .notifications import AdminNotificationService, TaskInfo


# Configure logging
logger = logging.getLogger(__name__)


# Task execution settings
TASK_TIMEOUT_SECONDS = 600  # 10 minutes
MAX_RETRIES = 2
STUCK_TASK_THRESHOLD_MINUTES = 30


class TaskTimeoutError(Exception):
    """Exception raised when task execution times out."""
    pass


@contextmanager
def timeout_handler(seconds: int):
    """
    Context manager for task timeout handling.

    On Windows, signal.SIGALRM is not available, so this uses
    a simpler approach that relies on external timeout (APScheduler's
    misfire_grace_time or job timeout settings).

    Args:
        seconds: Timeout in seconds (informational on Windows).

    Yields:
        None

    Note:
        On Unix systems, this would use signal.alarm for true timeout.
        On Windows, timeout is handled by APScheduler's job settings.
    """
    # On Windows, we can't use signal.SIGALRM
    # The actual timeout is enforced by APScheduler's job settings
    logger.debug(f"Task timeout set to {seconds} seconds")
    try:
        yield
    finally:
        logger.debug("Task timeout context exited")


def execute_improvement_task(
    task_id: str,
    autonomous: bool = False,
    retry_count: int = 0
) -> dict:
    """
    Execute a single improvement task.

    This is the main task execution function called by the scheduler.
    It wraps the executor logic with timeout, retry, and error handling.

    Args:
        task_id: UUID of the ImprovementTaskModel to execute.
        autonomous: If True, use AutonomousExecutor for LOW severity tasks.
        retry_count: Current retry attempt number (0 = first attempt).

    Returns:
        Dictionary with execution result:
            - success: bool
            - message: str
            - task_id: str
            - retried: bool (if retry was attempted)
    """
    logger.info(f"Starting execution of task {task_id} (retry={retry_count}, autonomous={autonomous})")

    try:
        # Fetch the task
        task = ImprovementTaskModel.objects.get(id=task_id)
    except ImprovementTaskModel.DoesNotExist:
        logger.error(f"Task {task_id} not found")
        return {
            'success': False,
            'message': f"Task {task_id} not found",
            'task_id': task_id,
            'retried': False
        }

    # Create appropriate executor
    if autonomous:
        executor = AutonomousExecutor()
    else:
        executor = ImprovementExecutor()

    try:
        with timeout_handler(TASK_TIMEOUT_SECONDS):
            result = executor.execute_task(task)

        if result.success:
            logger.info(f"Task {task_id} completed successfully")
            return {
                'success': True,
                'message': result.message,
                'task_id': task_id,
                'retried': retry_count > 0
            }
        else:
            # Execution failed
            logger.warning(f"Task {task_id} execution failed: {result.message}")

            # Check if we should retry
            if retry_count < MAX_RETRIES:
                logger.info(f"Scheduling retry {retry_count + 1}/{MAX_RETRIES} for task {task_id}")
                # Note: In a real async system, this would schedule another job
                # For APScheduler, the retry happens in the periodic task processor
                return {
                    'success': False,
                    'message': result.message,
                    'task_id': task_id,
                    'retried': False,
                    'should_retry': True
                }
            else:
                logger.error(f"Task {task_id} failed after {MAX_RETRIES} retries")
                return {
                    'success': False,
                    'message': f"Failed after {MAX_RETRIES} retries: {result.message}",
                    'task_id': task_id,
                    'retried': True
                }

    except TaskTimeoutError:
        logger.error(f"Task {task_id} timed out after {TASK_TIMEOUT_SECONDS} seconds")
        # Update task status to ERROR
        try:
            task.transition_status(
                ImprovementTaskModel.STATUS_ERROR,
                error_message=f"Execution timed out after {TASK_TIMEOUT_SECONDS} seconds"
            )
        except Exception as e:
            logger.error(f"Failed to update task {task_id} status: {e}")

        return {
            'success': False,
            'message': f"Execution timed out after {TASK_TIMEOUT_SECONDS} seconds",
            'task_id': task_id,
            'retried': False
        }

    except Exception as e:
        logger.exception(f"Unexpected error executing task {task_id}: {e}")
        return {
            'success': False,
            'message': f"Unexpected error: {e}",
            'task_id': task_id,
            'retried': False
        }


def process_approved_tasks() -> dict:
    """
    Process all tasks that are APPROVED and ready for execution.

    This is a periodic task that runs every 5 minutes to find
    approved tasks and execute them.

    Returns:
        Dictionary with processing results:
            - processed: int (number of tasks processed)
            - succeeded: int (number of successful executions)
            - failed: int (number of failed executions)
            - tasks: list of task_id results
    """
    logger.info("Running process_approved_tasks job...")

    # Find all APPROVED tasks
    approved_tasks = ImprovementTaskModel.objects.filter(
        status=ImprovementTaskModel.STATUS_APPROVED
    ).order_by('created_at')

    results = {
        'processed': 0,
        'succeeded': 0,
        'failed': 0,
        'tasks': []
    }

    for task in approved_tasks:
        results['processed'] += 1
        logger.info(f"Processing approved task {task.id}: {task.title}")

        # Execute the task
        result = execute_improvement_task(str(task.id), autonomous=False)
        results['tasks'].append(result)

        if result['success']:
            results['succeeded'] += 1
        else:
            results['failed'] += 1

    if results['processed'] > 0:
        logger.info(
            f"Processed {results['processed']} approved tasks: "
            f"{results['succeeded']} succeeded, {results['failed']} failed"
        )
    else:
        logger.debug("No approved tasks to process")

    return results


def process_autonomous_tasks() -> dict:
    """
    Process all LOW severity tasks that are ready for autonomous execution.

    This is a periodic task that runs every 5 minutes to find
    tasks that can be auto-executed without admin approval.

    Returns:
        Dictionary with processing results:
            - processed: int (number of tasks processed)
            - succeeded: int (number of successful executions)
            - failed: int (number of failed executions)
            - skipped: int (number of tasks skipped - not safe)
            - tasks: list of task_id results
    """
    logger.info("Running process_autonomous_tasks job...")

    # Find all LOW severity tasks that don't require approval
    autonomous_tasks = ImprovementTaskModel.objects.filter(
        status=ImprovementTaskModel.STATUS_NEW,
        severity=ImprovementTaskModel.SEVERITY_LOW,
        requires_approval=False
    ).order_by('created_at')

    results = {
        'processed': 0,
        'succeeded': 0,
        'failed': 0,
        'skipped': 0,
        'tasks': []
    }

    executor = AutonomousExecutor()

    for task in autonomous_tasks:
        results['processed'] += 1
        logger.info(f"Processing autonomous task {task.id}: {task.title}")

        # Double-check safety before execution
        is_safe, reason = executor.is_safe_for_autonomous(task)
        if not is_safe:
            logger.warning(f"Task {task.id} skipped - not safe: {reason}")
            results['skipped'] += 1
            results['tasks'].append({
                'success': False,
                'message': f"Skipped - not safe: {reason}",
                'task_id': str(task.id),
                'skipped': True
            })
            continue

        # Execute the task
        result = execute_improvement_task(str(task.id), autonomous=True)
        results['tasks'].append(result)

        if result['success']:
            results['succeeded'] += 1
        else:
            results['failed'] += 1

    if results['processed'] > 0:
        logger.info(
            f"Processed {results['processed']} autonomous tasks: "
            f"{results['succeeded']} succeeded, {results['failed']} failed, "
            f"{results['skipped']} skipped"
        )
    else:
        logger.debug("No autonomous tasks to process")

    return results


def monitor_stuck_tasks() -> dict:
    """
    Monitor and alert on tasks that have been IN_PROGRESS for too long.

    Tasks stuck IN_PROGRESS for more than 30 minutes are likely hung
    and need admin attention.

    Returns:
        Dictionary with monitoring results:
            - stuck_count: int (number of stuck tasks found)
            - notified: bool (whether admin was notified)
            - tasks: list of stuck task IDs
    """
    logger.info("Running stuck task monitor...")

    threshold = timezone.now() - timedelta(minutes=STUCK_TASK_THRESHOLD_MINUTES)

    # Find tasks that have been IN_PROGRESS too long
    stuck_tasks = ImprovementTaskModel.objects.filter(
        status=ImprovementTaskModel.STATUS_IN_PROGRESS,
        updated_at__lt=threshold
    )

    results = {
        'stuck_count': stuck_tasks.count(),
        'notified': False,
        'tasks': []
    }

    if results['stuck_count'] > 0:
        logger.warning(f"Found {results['stuck_count']} stuck tasks!")

        for task in stuck_tasks:
            results['tasks'].append(str(task.id))
            logger.warning(
                f"Stuck task {task.id}: {task.title} "
                f"(in_progress since {task.updated_at})"
            )

        # Notify admin
        try:
            notification_service = AdminNotificationService()
            # Create a summary task info
            task_info = TaskInfo(
                task_id='monitor',
                title=f"Stuck Task Alert: {results['stuck_count']} tasks",
                description=f"Tasks in IN_PROGRESS for more than {STUCK_TASK_THRESHOLD_MINUTES} minutes",
                severity='high'
            )
            notification_service.notify_task_error(
                task=task_info,
                error_details=f"Stuck tasks: {', '.join(results['tasks'])}",
                rollback_successful=False,
                rollback_hash=None
            )
            results['notified'] = True
            logger.info("Admin notified of stuck tasks")
        except Exception as e:
            logger.error(f"Failed to notify admin of stuck tasks: {e}")

    else:
        logger.debug("No stuck tasks found")

    return results


def get_queue_status() -> dict:
    """
    Get current status of the task queue.

    Returns:
        Dictionary with queue status:
            - pending_approval: int
            - approved: int (ready to execute)
            - autonomous: int (ready for auto-execution)
            - in_progress: int
            - stuck: int (in_progress > 30min)
            - completed_today: int
            - errors_today: int
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stuck_threshold = now - timedelta(minutes=STUCK_TASK_THRESHOLD_MINUTES)

    status = {
        'pending_approval': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL
        ).count(),
        'approved': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_APPROVED
        ).count(),
        'autonomous': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_NEW,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            requires_approval=False
        ).count(),
        'in_progress': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_IN_PROGRESS
        ).count(),
        'stuck': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_IN_PROGRESS,
            updated_at__lt=stuck_threshold
        ).count(),
        'completed_today': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_COMPLETED,
            completed_at__gte=today_start
        ).count(),
        'errors_today': ImprovementTaskModel.objects.filter(
            status=ImprovementTaskModel.STATUS_ERROR,
            updated_at__gte=today_start
        ).count(),
    }

    return status


def run_health_check() -> dict:
    """
    Run a system health check.

    This is a periodic task designed to run every 15 minutes to monitor
    system health and take appropriate actions if issues are detected.

    Returns:
        Dictionary with health check results:
            - timestamp: ISO timestamp of check
            - status: 'healthy', 'degraded', or 'critical'
            - reason: Human-readable status reason
            - error_rate: Current error rate percentage
            - rollback_rate: Current rollback rate percentage
            - consecutive_failures: Number of consecutive failures
            - actions: Dictionary of actions taken
    """
    logger.info("Running scheduled health check...")
    return _run_health_check()
