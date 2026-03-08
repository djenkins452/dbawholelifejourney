"""
Scheduler Health — APScheduler liveness check and auto-restart.

The APScheduler instance runs in-process with Gunicorn. If the scheduler
thread dies (OOM, exception, deadlock) while Gunicorn stays alive, ISE
and all downstream engines stop running. This module detects that state
and can restart the scheduler without a full container restart.

Public API:
    get_scheduler_status() -> dict
    restart_scheduler() -> dict
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_scheduler():
    """Get the APScheduler instance from wsgi module."""
    try:
        import config.wsgi as wsgi_module
        return getattr(wsgi_module, '_scheduler_instance', None)
    except Exception:
        return None


def get_scheduler_status():
    """
    Check APScheduler health.

    Works across Gunicorn workers: only one worker owns the scheduler
    (protected by DB lock). When a non-owner worker handles this request,
    we check the SchedulerLock and SchedulerHeartbeat in the DB instead
    of relying on the in-process _scheduler_instance.

    Returns dict with:
        running: bool — is the scheduler thread alive (or lock fresh)
        job_count: int — number of registered jobs (0 if not owner worker)
        last_heartbeat: str — ISO timestamp of last ISE heartbeat
        drift_seconds: int — seconds since last heartbeat
        status: str — ALIVE / DELAYED / OFFLINE / NOT_STARTED / NO_HEARTBEAT
        needs_restart: bool — True if scheduler should be restarted
        scheduler_owner: str — which worker holds the lock (if known)
    """
    result = {
        'running': False,
        'job_count': 0,
        'last_heartbeat': None,
        'drift_seconds': None,
        'status': 'NOT_STARTED',
        'needs_restart': False,
        'scheduler_owner': None,
    }

    scheduler = _get_scheduler()

    if scheduler is not None:
        # This worker owns the scheduler — check thread directly
        try:
            result['running'] = scheduler.running
            result['job_count'] = len(scheduler.get_jobs())
        except Exception as e:
            logger.warning("Scheduler health: error checking scheduler state: %s", e)
            result['status'] = 'ERROR'
            result['needs_restart'] = True
            return result

        if not scheduler.running:
            result['status'] = 'STOPPED'
            result['needs_restart'] = True
            return result
    else:
        # This worker does NOT own the scheduler — check DB lock to see
        # if another worker has it running
        try:
            from apps.core.ai_scheduler.scheduler_models import SchedulerLock
            lock = SchedulerLock.objects.filter(lock_name='apscheduler_main').first()
            if lock:
                age = (timezone.now() - lock.locked_at).total_seconds()
                result['scheduler_owner'] = lock.locked_by
                if age < 600:  # LOCK_TIMEOUT_SECONDS
                    # Lock is fresh — scheduler running in another worker
                    result['running'] = True
                else:
                    # Lock is stale — scheduler likely dead
                    result['status'] = 'OFFLINE'
                    result['needs_restart'] = True
                    return result
            else:
                result['status'] = 'NOT_STARTED'
                result['needs_restart'] = True
                return result
        except Exception as e:
            logger.warning("Scheduler health: lock check failed: %s", e)

    # Check heartbeat from DB (works regardless of which worker we're on)
    try:
        from apps.core.ai_observability.models import SchedulerHeartbeat
        hb = SchedulerHeartbeat.objects.filter(scheduler_name='ISE').first()
        if hb:
            result['last_heartbeat'] = hb.last_tick_at.isoformat()
            drift = (timezone.now() - hb.last_tick_at).total_seconds()
            result['drift_seconds'] = int(drift)

            # ISE expected interval: 300s (5 min)
            # Thresholds: ALIVE <= 450s, DELAYED <= 900s, OFFLINE > 900s
            expected = hb.expected_interval_seconds or 300
            alive_threshold = expected * (hb.alive_threshold_multiplier or 1.5)
            offline_threshold = expected * (hb.offline_threshold_multiplier or 3.0)

            if drift <= alive_threshold:
                result['status'] = 'ALIVE'
            elif drift <= offline_threshold:
                result['status'] = 'DELAYED'
            else:
                result['status'] = 'OFFLINE'
                result['needs_restart'] = True
        else:
            # No heartbeat record — scheduler may have just started
            result['status'] = 'NO_HEARTBEAT'
    except Exception as e:
        logger.debug("Scheduler health: heartbeat check failed: %s", e)

    # Even if running is True, a stale heartbeat means the ISE job is hung
    if result['running'] and result.get('drift_seconds') and result['drift_seconds'] > 900:
        result['needs_restart'] = True

    return result


def restart_scheduler():
    """
    Restart the APScheduler if it's stopped or unhealthy.

    Steps:
        1. Shut down existing scheduler (if any)
        2. Clear the SCHEDULER_STARTED env var
        3. Call start_scheduler() from wsgi to reinitialize
        4. Return status

    Returns dict with:
        success: bool
        message: str
        status: dict — new scheduler status after restart
    """
    import os

    logger.warning("Scheduler restart requested")

    # Step 1: Shut down existing scheduler
    scheduler = _get_scheduler()
    if scheduler is not None:
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
                logger.info("Existing scheduler shut down")
        except Exception as e:
            logger.warning("Error shutting down scheduler: %s", e)

    # Step 2: Clear environment guard so start_scheduler() will proceed
    os.environ.pop('SCHEDULER_STARTED', None)

    # Step 3: Clear module-level reference
    try:
        import config.wsgi as wsgi_module
        wsgi_module._scheduler_instance = None
    except Exception:
        pass

    # Step 4: Re-run start_scheduler()
    try:
        from config.wsgi import start_scheduler
        start_scheduler()

        # Step 5: Verify
        new_status = get_scheduler_status()
        success = new_status.get('running', False)

        if success:
            logger.info("Scheduler restarted successfully")
        else:
            logger.error("Scheduler restart failed — still not running")

        return {
            'success': success,
            'message': 'Scheduler restarted' if success else 'Restart failed',
            'status': new_status,
        }

    except Exception as e:
        logger.exception("Scheduler restart failed: %s", e)
        return {
            'success': False,
            'message': f'Restart error: {str(e)[:200]}',
            'status': get_scheduler_status(),
        }
