"""
Whole Life Journey - Celery Tasks (Core Module)

Project: Whole Life Journey
Path: apps/core/tasks.py
Purpose: Celery task definitions for core background processing

Description:
    Celery tasks that wrap existing job functions. Tasks are thin wrappers —
    all business logic lives in the job functions or engine modules.

    Currently handles:
    - SAME (System Autonomous Monitoring Engine) cycle execution

Tasks:
    - run_same_cycle_task: Triggers SAME monitoring cycle every 60 seconds

Note:
    The DB lock in run_same_cycle() prevents duplicate execution even if
    multiple workers pick up the same task. Celery is only the trigger.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger("celery.tasks")


@shared_task(
    bind=True,
    name="apps.core.tasks.run_same_cycle_task",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_same_cycle_task(self):
    """
    Celery task wrapper for SAME monitoring cycle.

    Calls run_same_cycle() which:
    - Acquires DB lock (SchedulerLock)
    - Computes heartbeats for all engines
    - Detects anomalies (7 detectors)
    - Escalates aged anomalies
    - Runs autonomous remediation (if enabled)
    - Generates narrative snapshot
    - Computes System Integrity Index
    - Releases DB lock

    The DB lock prevents duplicate execution even if multiple workers
    or beat instances trigger this task simultaneously.

    Writes SAMEExecutionLog entries for observability in the Ops Wall.
    """
    task_id = self.request.id or "local"
    start = time.monotonic()
    logger.info(f"SAME Celery task starting (task_id={task_id})")

    # Find or create execution log for this task
    execution_log = _get_or_create_execution_log(task_id)

    try:
        # Mark as running
        if execution_log:
            execution_log.status = "running"
            execution_log.save(update_fields=["status"])

        from apps.core.jobs import run_same_cycle

        run_same_cycle()

        duration = time.monotonic() - start
        duration_ms = int(duration * 1000)
        logger.info(
            f"SAME Celery task completed "
            f"(task_id={task_id}, duration={duration:.2f}s)"
        )

        # Mark completed
        if execution_log:
            _complete_execution_log(execution_log, "completed", duration_ms)

        return {
            "status": "ok",
            "duration_seconds": round(duration, 2),
            "task_id": task_id,
        }

    except SoftTimeLimitExceeded:
        duration = time.monotonic() - start
        duration_ms = int(duration * 1000)
        logger.warning(
            f"SAME Celery task hit soft time limit "
            f"(task_id={task_id}, duration={duration:.2f}s)"
        )
        if execution_log:
            _complete_execution_log(execution_log, "timeout", duration_ms)
        # Do NOT retry on timeout — the DB lock will expire naturally
        # and the next scheduled beat will pick it up
        return {
            "status": "timeout",
            "duration_seconds": round(duration, 2),
            "task_id": task_id,
        }

    except Exception as exc:
        duration = time.monotonic() - start
        duration_ms = int(duration * 1000)
        logger.exception(
            f"SAME Celery task failed "
            f"(task_id={task_id}, duration={duration:.2f}s, "
            f"retry={self.request.retries}/{self.max_retries}): {exc}"
        )
        # Retry on transient failures (DB connection, etc.)
        # DB lock will be released by finally block in run_same_cycle()
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                f"SAME Celery task max retries exceeded "
                f"(task_id={task_id})"
            )
            if execution_log:
                _complete_execution_log(
                    execution_log, "failed", duration_ms,
                    error_detail=f"Max retries exceeded: {str(exc)[:400]}",
                )
            return {
                "status": "max_retries_exceeded",
                "duration_seconds": round(duration, 2),
                "task_id": task_id,
            }


def _get_or_create_execution_log(task_id):
    """
    Find existing SAMEExecutionLog for this task_id (manual trigger),
    or create one for scheduled execution.
    """
    try:
        from django.utils import timezone as tz

        from apps.core.ai_observability.models import SAMEExecutionLog

        # Check if a manual trigger already created a log for this task
        existing = SAMEExecutionLog.objects.filter(
            celery_task_id=task_id,
            status="queued",
        ).first()
        if existing:
            return existing

        # Create new log for scheduled execution
        return SAMEExecutionLog.objects.create(
            trigger_source="scheduled",
            status="queued",
            celery_task_id=task_id,
        )
    except Exception:
        logger.warning("Failed to create SAMEExecutionLog", exc_info=True)
        return None


def _complete_execution_log(execution_log, status, duration_ms, error_detail=""):
    """Update SAMEExecutionLog with final status."""
    try:
        from django.utils import timezone as tz

        execution_log.status = status
        execution_log.completed_at = tz.now()
        execution_log.duration_ms = duration_ms
        if error_detail:
            execution_log.error_detail = error_detail
        execution_log.save(
            update_fields=["status", "completed_at", "duration_ms", "error_detail"]
        )
    except Exception:
        logger.warning("Failed to update SAMEExecutionLog", exc_info=True)
