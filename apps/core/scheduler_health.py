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

    Returns dict with:
        running: bool — is the scheduler thread alive
        job_count: int — number of registered jobs
        last_heartbeat: str — ISO timestamp of last ISE heartbeat
        drift_seconds: int — seconds since last heartbeat
        status: str — ALIVE / DELAYED / OFFLINE / NOT_STARTED
        needs_restart: bool — True if scheduler should be restarted
    """
    result = {
        'running': False,
        'job_count': 0,
        'last_heartbeat': None,
        'drift_seconds': None,
        'status': 'NOT_STARTED',
        'needs_restart': False,
    }

    scheduler = _get_scheduler()

    if scheduler is None:
        result['status'] = 'NOT_STARTED'
        result['needs_restart'] = True
        return result

    # Check if the APScheduler thread is alive
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

    # Check heartbeat from DB
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
