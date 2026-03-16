"""
Scheduler Health — Celery Beat liveness check.

All background scheduling is handled by Celery Beat (separate process).
APScheduler was removed in 2026-03-16.

This module provides health status by checking:
  1. ISE heartbeat (SchedulerHeartbeat) — is the ISE cycle running?
  2. SAME heartbeat — is SAME monitoring running?
  3. Celery Beat heartbeat — is the Beat process dispatching tasks?

Public API:
    get_scheduler_status() -> dict
"""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_scheduler_status():
    """
    Check Celery Beat scheduling health.

    Derives health from ISE and SAME heartbeats. If both are current,
    Celery Beat is alive and dispatching tasks. If both are stale,
    Celery Beat is likely dead.

    Returns dict with:
        running: bool — is scheduling infrastructure healthy
        status: str — ALIVE / DELAYED / OFFLINE
        ise_status: str — ISE heartbeat status
        same_status: str — SAME heartbeat status
        drift_seconds: int — ISE heartbeat drift (primary indicator)
        needs_restart: bool — True if Beat process should be investigated
    """
    result = {
        'running': False,
        'status': 'OFFLINE',
        'ise_status': 'OFFLINE',
        'same_status': 'OFFLINE',
        'drift_seconds': None,
        'needs_restart': False,
    }

    try:
        from apps.core.ai_observability.models import SchedulerHeartbeat

        # ISE heartbeat (primary indicator — runs every 5 min via Beat)
        ise_hb = SchedulerHeartbeat.get_for_scheduler("ISE")
        ise_status = ise_hb.status if ise_hb else "OFFLINE"
        result['ise_status'] = ise_status
        if ise_hb:
            result['drift_seconds'] = int(
                (timezone.now() - ise_hb.last_tick_at).total_seconds()
            )

        # SAME heartbeat (secondary — runs every 60s via Beat)
        same_hb = SchedulerHeartbeat.get_for_scheduler("SAME")
        same_status = same_hb.status if same_hb else "OFFLINE"
        result['same_status'] = same_status

        # Derive overall status from both heartbeats
        if ise_status == "ALIVE" and same_status == "ALIVE":
            result['status'] = 'ALIVE'
            result['running'] = True
        elif ise_status == "ALIVE" or same_status == "ALIVE":
            result['status'] = 'DELAYED'
            result['running'] = True
            result['needs_restart'] = True
        elif ise_status == "DELAYED" or same_status == "DELAYED":
            result['status'] = 'DELAYED'
            result['running'] = True
            result['needs_restart'] = True
        else:
            result['status'] = 'OFFLINE'
            result['needs_restart'] = True

    except Exception as e:
        logger.warning("Scheduler health check failed: %s", e)
        result['status'] = 'ERROR'

    return result
