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
    """
    task_id = self.request.id or "local"
    start = time.monotonic()
    logger.info(f"SAME Celery task starting (task_id={task_id})")

    try:
        from apps.core.jobs import run_same_cycle

        run_same_cycle()

        duration = time.monotonic() - start
        logger.info(
            f"SAME Celery task completed "
            f"(task_id={task_id}, duration={duration:.2f}s)"
        )
        return {
            "status": "ok",
            "duration_seconds": round(duration, 2),
            "task_id": task_id,
        }

    except SoftTimeLimitExceeded:
        duration = time.monotonic() - start
        logger.warning(
            f"SAME Celery task hit soft time limit "
            f"(task_id={task_id}, duration={duration:.2f}s)"
        )
        # Do NOT retry on timeout — the DB lock will expire naturally
        # and the next scheduled beat will pick it up
        return {
            "status": "timeout",
            "duration_seconds": round(duration, 2),
            "task_id": task_id,
        }

    except Exception as exc:
        duration = time.monotonic() - start
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
            return {
                "status": "max_retries_exceeded",
                "duration_seconds": round(duration, 2),
                "task_id": task_id,
            }
