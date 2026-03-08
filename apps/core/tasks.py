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
    - ISE (Intelligence Scheduler Engine) cycle execution (redundant trigger)
    - ISE engine execution (dispatched from scheduler with EngineRun telemetry)

Tasks:
    - run_same_cycle_task: Triggers SAME monitoring cycle every 60 seconds
    - run_ise_cycle_task: Triggers ISE scheduler cycle every 5 minutes
      (redundant with APScheduler — ensures ISE survives scheduler thread death)
    - run_ise_engine_task: Executes individual ISE engines with EngineRun telemetry

Note:
    The DB lock in run_same_cycle() prevents duplicate execution even if
    multiple workers pick up the same task. Celery is only the trigger.

    ISE dedup is handled by ScheduledIntelligenceTask.next_run_at — tasks
    that have already run (via APScheduler or Celery) won't re-execute.

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

        # Record SAME scheduler heartbeat (fail-silent)
        try:
            from apps.core.ai_observability.models import SchedulerHeartbeat

            SchedulerHeartbeat.tick(
                scheduler_name=SchedulerHeartbeat.SCHEDULER_SAME,
                expected_interval_seconds=60,  # Celery beat every 60s
                cycle_result={"duration_ms": duration_ms},
            )
        except Exception:
            pass

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


# =========================================================================
# ISE (INTELLIGENCE SCHEDULER ENGINE) — REDUNDANT CELERY BEAT TRIGGER
# =========================================================================


@shared_task(
    bind=True,
    name="apps.core.tasks.run_ise_cycle_task",
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=240,
)
def run_ise_cycle_task(self):
    """
    Celery Beat redundant trigger for ISE scheduler cycle.

    Provides resilience against APScheduler thread death. The ISE also runs
    every 5 minutes via APScheduler in the Gunicorn web process (wsgi.py).
    If APScheduler is alive, both triggers fire but tasks only execute once
    (ScheduledIntelligenceTask.next_run_at prevents double-execution).

    If the APScheduler thread dies (which caused ISE to go offline for 51+
    minutes), this Celery Beat task keeps ISE alive independently.
    """
    task_id = self.request.id or "local"
    start = time.monotonic()
    logger.info("ISE Celery Beat task starting (task_id=%s)", task_id)

    try:
        from apps.core.ai_scheduler.scheduler_engine import run_scheduler_cycle

        result = run_scheduler_cycle()

        duration = time.monotonic() - start
        logger.info(
            "ISE Celery Beat task completed "
            "(task_id=%s, duration=%.2fs, executed=%d, skipped=%d, failed=%d)",
            task_id, duration,
            result["executed"], result["skipped"], result["failed"],
        )

        return {
            "status": "ok",
            "duration_seconds": round(duration, 2),
            "task_id": task_id,
            "result": result,
        }

    except SoftTimeLimitExceeded:
        duration = time.monotonic() - start
        logger.warning(
            "ISE Celery Beat task hit soft time limit (task_id=%s, duration=%.2fs)",
            task_id, duration,
        )
        return {"status": "timeout", "task_id": task_id}

    except Exception as exc:
        duration = time.monotonic() - start
        logger.exception(
            "ISE Celery Beat task failed (task_id=%s, duration=%.2fs): %s",
            task_id, duration, exc,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("ISE Celery Beat task max retries exceeded (task_id=%s)", task_id)
            return {"status": "max_retries_exceeded", "task_id": task_id}


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


# =========================================================================
# ISE ENGINE EXECUTION TASK (Dispatched from scheduler)
# =========================================================================


@shared_task(
    bind=True,
    name="apps.core.tasks.run_ise_engine_task",
    max_retries=1,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=600,
    soft_time_limit=300,
)
def run_ise_engine_task(self, task_name):
    """
    Execute an ISE-scheduled engine in a Celery worker with EngineRun telemetry.

    Dispatched by the ISE scheduler (scheduler_engine._execute_task) when a
    task is due. Wraps the runner function with run_engine() to create
    EngineRun records visible to COAS monitoring.

    Updates ScheduledIntelligenceTask status after completion.

    Args:
        task_name: ISE task name from scheduler_registry (e.g.,
            "update_learning_profiles", "generate_daily_briefings").
    """
    task_id = self.request.id or "local"
    start = time.monotonic()
    logger.info(
        "ISE engine task starting: %s (task_id=%s)", task_name, task_id,
    )

    try:
        from apps.core.ai_scheduler.scheduler_registry import get_task_function
        from apps.core.engine_runtime import get_engine_name, run_engine

        task_func = get_task_function(task_name)
        if not task_func:
            _update_ise_task_status(task_name, "failed", f"No runner for {task_name}")
            raise ValueError(f"No runner registered for ISE task: {task_name}")

        engine_name = get_engine_name(task_name)
        result = run_engine(engine_name, task_func)

        duration_ms = int((time.monotonic() - start) * 1000)
        _update_ise_task_status(task_name, "success")
        logger.info(
            "ISE engine task completed: %s (%dms, task_id=%s)",
            task_name, duration_ms, task_id,
        )
        return {
            "status": "ok",
            "task_name": task_name,
            "engine": engine_name,
            "duration_ms": duration_ms,
            "result": result if isinstance(result, dict) else None,
        }

    except SoftTimeLimitExceeded:
        duration_ms = int((time.monotonic() - start) * 1000)
        _update_ise_task_status(task_name, "failed", "Soft time limit exceeded")
        logger.warning(
            "ISE engine task hit soft time limit: %s (%dms)", task_name, duration_ms,
        )
        return {"status": "timeout", "task_name": task_name}

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        _update_ise_task_status(task_name, "failed", str(exc)[:1000])
        logger.exception(
            "ISE engine task failed: %s (%dms)", task_name, duration_ms,
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "ISE engine task max retries exceeded: %s (task_id=%s)",
                task_name, task_id,
            )
            return {"status": "failed", "task_name": task_name}


def _update_ise_task_status(task_name, status, error=""):
    """Update ScheduledIntelligenceTask status after Celery execution."""
    try:
        from django.db.models import F

        from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask

        updates = {
            "last_status": status,
            "last_error": error[:1000] if error else "",
        }
        ScheduledIntelligenceTask.objects.filter(
            task_name=task_name,
        ).update(**updates)

        # Increment run_count atomically on success
        if status == "success":
            ScheduledIntelligenceTask.objects.filter(
                task_name=task_name,
            ).update(run_count=F("run_count") + 1)
    except Exception:
        logger.warning(
            "Failed to update ISE task status for %s", task_name, exc_info=True,
        )


# =========================================================================
# PER-ENGINE EXECUTION TASK (Manual trigger from Ops Wall)
# =========================================================================


@shared_task(
    bind=True,
    name="apps.core.tasks.run_engine_task",
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,
)
def run_engine_task(self, engine_name, execution_log_id):
    """
    Generic Celery task for running any manually-executable engine.

    Resolves the batch runner from ENGINE_REGISTRY, executes it,
    and updates the EngineExecutionLog with result/duration.

    Args:
        engine_name: Engine code (DBE, WIRE, DNE, PGE)
        execution_log_id: PK of EngineExecutionLog to update
    """
    task_id = self.request.id or "local"
    start = time.monotonic()
    logger.info(
        "Engine task starting: %s (execution_log=%s, task_id=%s)",
        engine_name, execution_log_id, task_id,
    )

    # Load execution log
    execution_log = _get_engine_execution_log(execution_log_id, task_id)

    try:
        # Mark as running
        if execution_log:
            execution_log.status = "running"
            execution_log.save(update_fields=["status"])

        # Resolve and call the batch runner
        from apps.core.ai_observability.engine_registry import resolve_batch_runner

        runner = resolve_batch_runner(engine_name)
        if not runner:
            raise ValueError(f"No batch runner configured for engine {engine_name}")

        result = runner()

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Engine task completed: %s (%dms, result=%s)",
            engine_name, duration_ms, result,
        )

        if execution_log:
            _finish_engine_execution_log(
                execution_log, "completed", duration_ms, result_summary=result,
            )

        # Post-execution recovery: recompute heartbeats + integrity score
        # so the UI reflects the recovery immediately (no 60s SAME-cycle wait)
        try:
            from apps.core.ai_observability.same_engine import (
                recompute_integrity_after_recovery,
            )

            recompute_integrity_after_recovery(engine_name)
        except Exception:
            logger.warning(
                "Post-execution recovery failed for %s", engine_name, exc_info=True,
            )

        return {
            "status": "ok",
            "engine": engine_name,
            "duration_ms": duration_ms,
            "result": result,
        }

    except SoftTimeLimitExceeded:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "Engine task hit soft time limit: %s (%dms)", engine_name, duration_ms,
        )
        if execution_log:
            _finish_engine_execution_log(execution_log, "timeout", duration_ms)
        return {"status": "timeout", "engine": engine_name}

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Engine task failed: %s (%dms)", engine_name, duration_ms)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "Engine task max retries exceeded: %s (task_id=%s)",
                engine_name, task_id,
            )
            if execution_log:
                _finish_engine_execution_log(
                    execution_log, "failed", duration_ms,
                    error_detail=f"Max retries exceeded: {str(exc)[:400]}",
                )
            return {
                "status": "failed",
                "engine": engine_name,
                "error": str(exc)[:200],
            }


def _get_engine_execution_log(execution_log_id, task_id):
    """Load EngineExecutionLog by ID and update its celery_task_id."""
    try:
        from apps.core.ai_observability.models import EngineExecutionLog

        log = EngineExecutionLog.objects.filter(pk=execution_log_id).first()
        if log and not log.celery_task_id:
            log.celery_task_id = task_id
            log.save(update_fields=["celery_task_id"])
        return log
    except Exception:
        logger.warning(
            "Failed to load EngineExecutionLog %s", execution_log_id, exc_info=True,
        )
        return None


def _finish_engine_execution_log(
    execution_log, status, duration_ms, result_summary=None, error_detail="",
):
    """Update EngineExecutionLog with final status."""
    try:
        from django.utils import timezone as tz

        execution_log.status = status
        execution_log.completed_at = tz.now()
        execution_log.duration_ms = duration_ms
        update_fields = ["status", "completed_at", "duration_ms"]
        if result_summary:
            execution_log.result_summary = result_summary
            update_fields.append("result_summary")
        if error_detail:
            execution_log.error_detail = error_detail
            update_fields.append("error_detail")
        execution_log.save(update_fields=update_fields)
    except Exception:
        logger.warning("Failed to update EngineExecutionLog", exc_info=True)
