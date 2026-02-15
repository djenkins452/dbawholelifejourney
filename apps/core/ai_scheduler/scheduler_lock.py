"""
ISE — Scheduler Lock.

Database-backed singleton lock to prevent duplicate scheduler instances
across Gunicorn workers, container restarts, or multi-instance deploys.

Works alongside the existing os.environ['SCHEDULER_STARTED'] check as
a second layer of protection.
"""

import logging
import os
import socket

from django.db import IntegrityError
from django.utils import timezone

logger = logging.getLogger(__name__)

# Lock is considered stale after this many seconds.
# If a process crashes without releasing, the lock expires naturally.
LOCK_TIMEOUT_SECONDS = 600  # 10 minutes


def acquire_scheduler_lock(lock_name="apscheduler_main"):
    """
    Attempt to acquire the scheduler singleton lock.

    Uses database row-level locking with a staleness timeout.
    If the lock exists and is recent (< 10 minutes), another
    scheduler is assumed running.

    Args:
        lock_name: Lock identifier (default: "apscheduler_main").

    Returns:
        bool — True if lock acquired, False if another scheduler holds it.
    """
    from apps.core.ai_scheduler.scheduler_models import SchedulerLock

    now = timezone.now()
    locked_by = f"{socket.gethostname()}-{os.getpid()}"
    stale_threshold = timezone.timedelta(seconds=LOCK_TIMEOUT_SECONDS)

    try:
        lock, created = SchedulerLock.objects.get_or_create(
            lock_name=lock_name,
            defaults={
                "locked_at": now,
                "locked_by": locked_by,
            },
        )

        if created:
            logger.info(f"ISE Lock: Acquired new lock '{lock_name}' by {locked_by}")
            return True

        # Lock exists — check if stale
        age = now - lock.locked_at
        if age > stale_threshold:
            # Stale lock — take it over
            lock.locked_at = now
            lock.locked_by = locked_by
            lock.save(update_fields=["locked_at", "locked_by"])
            logger.warning(
                f"ISE Lock: Took over stale lock '{lock_name}' "
                f"(was held by {lock.locked_by} for {age.total_seconds():.0f}s)"
            )
            return True

        # Lock is fresh — another scheduler is running
        logger.info(
            f"ISE Lock: Lock '{lock_name}' held by {lock.locked_by} "
            f"({age.total_seconds():.0f}s ago). Skipping scheduler start."
        )
        return False

    except IntegrityError:
        # Race condition — another process created it simultaneously
        logger.info(f"ISE Lock: Race condition on '{lock_name}', skipping.")
        return False
    except Exception as e:
        # Database not ready (e.g., during migration) — allow scheduler to start
        # with the env var check as fallback protection
        logger.warning(f"ISE Lock: Could not check lock ({e}). Allowing start.")
        return True


def refresh_scheduler_lock(lock_name="apscheduler_main"):
    """
    Refresh the lock timestamp to prevent staleness.

    Called periodically by the running scheduler to indicate it's still alive.

    Args:
        lock_name: Lock identifier.
    """
    from apps.core.ai_scheduler.scheduler_models import SchedulerLock

    try:
        locked_by = f"{socket.gethostname()}-{os.getpid()}"
        updated = SchedulerLock.objects.filter(
            lock_name=lock_name,
            locked_by=locked_by,
        ).update(locked_at=timezone.now())

        if updated:
            logger.debug(f"ISE Lock: Refreshed lock '{lock_name}'")
    except Exception:
        pass  # Non-critical — lock will just age out naturally


def release_scheduler_lock(lock_name="apscheduler_main"):
    """
    Release the scheduler lock on clean shutdown.

    Args:
        lock_name: Lock identifier.
    """
    from apps.core.ai_scheduler.scheduler_models import SchedulerLock

    try:
        locked_by = f"{socket.gethostname()}-{os.getpid()}"
        deleted = SchedulerLock.objects.filter(
            lock_name=lock_name,
            locked_by=locked_by,
        ).delete()

        if deleted[0]:
            logger.info(f"ISE Lock: Released lock '{lock_name}'")
    except Exception as e:
        logger.warning(f"ISE Lock: Could not release lock: {e}")
