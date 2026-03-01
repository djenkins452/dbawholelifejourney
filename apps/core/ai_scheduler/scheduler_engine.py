"""
ISE — Scheduler Engine.

Core scheduler logic. Checks which tasks are due and executes them.
Called by the management command on a cron schedule (every 5 minutes).
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask
from apps.core.ai_scheduler.scheduler_registry import (
    get_registered_tasks,
    get_task_function,
)

logger = logging.getLogger(__name__)


def run_scheduler_cycle():
    """
    Execute one scheduler cycle.

    Checks all active ScheduledIntelligenceTask records.
    For each task where current_time >= next_run_at:
      - Execute the registered function
      - Update last_run_at, next_run_at, last_status
      - Handle errors safely (never crash the cycle)

    On wake from container sleep, detects overdue tasks and runs them
    immediately (catch-up mode) so engines recover without waiting for
    their next scheduled interval.

    Returns:
        dict — {executed: int, skipped: int, failed: int, catch_up: bool}
    """
    # Ensure all registered tasks have database records
    _ensure_task_records()

    tasks = ScheduledIntelligenceTask.objects.filter(is_active=True)
    now = timezone.now()

    # Detect catch-up scenario: if scheduler itself is waking from sleep,
    # multiple tasks will be overdue. Log it for observability.
    overdue_tasks = [t for t in tasks if now >= t.next_run_at]
    catch_up = len(overdue_tasks) > len(tasks) // 2 and len(overdue_tasks) > 2
    if catch_up:
        total_overdue_seconds = sum(
            (now - t.next_run_at).total_seconds() for t in overdue_tasks
        )
        avg_overdue = total_overdue_seconds / len(overdue_tasks)
        logger.warning(
            f"ISE: Catch-up mode — {len(overdue_tasks)} tasks overdue "
            f"(avg {avg_overdue:.0f}s behind). Running all now."
        )

    executed = 0
    skipped = 0
    failed = 0

    for task in tasks:
        if now < task.next_run_at:
            skipped += 1
            continue

        success = _execute_task(task, now)
        if success:
            executed += 1
        else:
            failed += 1

    result = {
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
        "catch_up": catch_up,
    }

    logger.info(
        f"ISE: Scheduler cycle complete — "
        f"executed={executed}, skipped={skipped}, failed={failed}"
        + (" [CATCH-UP]" if catch_up else "")
    )

    # Record scheduler heartbeat (fail-silent — never crash the cycle)
    try:
        from apps.core.ai_observability.models import SchedulerHeartbeat

        SchedulerHeartbeat.tick(
            scheduler_name=SchedulerHeartbeat.SCHEDULER_ISE,
            expected_interval_seconds=300,  # Railway cron every 5 min
            cycle_result=result,
        )
    except Exception:
        pass

    return result


def _execute_task(task, now):
    """
    Execute a single scheduled task.

    Args:
        task: ScheduledIntelligenceTask instance.
        now: Current datetime.

    Returns:
        bool — True if successful, False if failed.
    """
    task_func = get_task_function(task.task_name)
    if not task_func:
        task.last_status = "failed"
        task.last_error = f"No function registered for {task.task_name}"
        task.save(update_fields=["last_status", "last_error", "updated_at"])
        logger.error(f"ISE: No function for task {task.task_name}")
        return False

    # Mark as running
    task.last_status = "running"
    task.save(update_fields=["last_status", "updated_at"])

    try:
        logger.info(f"ISE: Executing task {task.task_name}")
        result = task_func()

        # Success
        task.last_run_at = now
        task.next_run_at = now + timedelta(seconds=task.run_interval_seconds)
        task.last_status = "success"
        task.last_error = ""
        task.run_count += 1
        task.save(update_fields=[
            "last_run_at", "next_run_at", "last_status",
            "last_error", "run_count", "updated_at",
        ])

        logger.info(
            f"ISE: Task {task.task_name} completed successfully. "
            f"Next run: {task.next_run_at.isoformat()}"
        )
        return True

    except Exception as e:
        # Failure — still advance next_run_at to prevent infinite retry loops
        task.last_run_at = now
        task.next_run_at = now + timedelta(seconds=task.run_interval_seconds)
        task.last_status = "failed"
        task.last_error = str(e)[:1000]
        task.save(update_fields=[
            "last_run_at", "next_run_at", "last_status",
            "last_error", "updated_at",
        ])

        logger.error(
            f"ISE: Task {task.task_name} failed: {e}",
            exc_info=True,
        )
        return False


def _ensure_task_records():
    """
    Create ScheduledIntelligenceTask records for any registered tasks
    that don't yet have database entries.

    This auto-seeds the scheduler on first run.
    """
    registered = get_registered_tasks()

    for task_name, config in registered.items():
        _, created = ScheduledIntelligenceTask.objects.get_or_create(
            task_name=task_name,
            defaults={
                "description": config.get("description", ""),
                "run_interval_seconds": config["interval_seconds"],
                "next_run_at": timezone.now(),
            },
        )
        if created:
            logger.info(f"ISE: Created task record for {task_name}")
