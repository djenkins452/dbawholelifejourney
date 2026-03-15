"""
Celery Worker Health — Execution layer observability for the Ops Wall.

The WLJ execution pipeline is:
    APScheduler → ISE → Celery Tasks → Engines
    Celery Beat → Celery Tasks

If Celery workers die while schedulers remain healthy, the system appears
operational but no engines actually execute. This module detects that state.

Public API:
    get_celery_health() -> dict
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Thresholds for health classification
QUEUE_DEPTH_WARN = 20
QUEUE_DEPTH_CRITICAL = 50
FAILED_1H_WARN = 5
FAILED_1H_CRITICAL = 15

# Timeout for inspect() calls — must be short to avoid blocking the poll
INSPECT_TIMEOUT_SECONDS = 2.0


def _get_celery_app():
    """Import the Celery app lazily to avoid circular imports."""
    try:
        from config.celery import app
        return app
    except ImportError:
        return None


def _get_queue_depth():
    """
    Get the number of messages waiting in the default Celery queue.

    Uses Redis LLEN on the 'celery' queue key directly — this is
    non-blocking and fast (O(1) in Redis).
    """
    try:
        import redis
        broker_url = getattr(settings, "CELERY_BROKER_URL", None)
        if not broker_url:
            return None
        client = redis.Redis.from_url(broker_url, socket_timeout=2)
        depth = client.llen("celery")
        return depth
    except Exception as e:
        logger.debug("Celery health: queue depth check failed: %s", e)
        return None


def _get_worker_stats(app):
    """
    Inspect active Celery workers.

    Uses celery.control.inspect() with a short timeout. Returns None
    if workers are unreachable (timeout or connection error).
    """
    try:
        inspector = app.control.inspect(timeout=INSPECT_TIMEOUT_SECONDS)

        # ping() is the lightest check — returns {worker_name: {'ok': 'pong'}}
        ping_result = inspector.ping()
        if not ping_result:
            return {"workers": [], "active_tasks": 0, "reserved_tasks": 0}

        worker_names = list(ping_result.keys())

        # Get active (currently executing) tasks per worker
        active = inspector.active() or {}
        # Get reserved (prefetched, waiting to execute) tasks per worker
        reserved = inspector.reserved() or {}
        # Get worker stats (processed count, uptime, etc.)
        stats = inspector.stats() or {}

        workers = []
        total_active = 0
        total_reserved = 0

        for name in worker_names:
            worker_active = active.get(name, [])
            worker_reserved = reserved.get(name, [])
            worker_stats = stats.get(name, {})
            active_count = len(worker_active)
            reserved_count = len(worker_reserved)

            total_active += active_count
            total_reserved += reserved_count

            # Extract useful stats
            total_processed = worker_stats.get("total", {})
            pool = worker_stats.get("pool", {})
            concurrency = pool.get("max-concurrency", None)

            workers.append({
                "name": name,
                "status": "online",
                "active_tasks": active_count,
                "reserved_tasks": reserved_count,
                "processed": sum(total_processed.values()) if isinstance(total_processed, dict) else 0,
                "concurrency": concurrency,
            })

        return {
            "workers": workers,
            "active_tasks": total_active,
            "reserved_tasks": total_reserved,
        }

    except Exception as e:
        logger.debug("Celery health: worker inspect failed: %s", e)
        return None


def _get_failed_task_count_1h():
    """
    Count engine execution failures in the last hour.

    Uses EngineRun records rather than Celery result backend, since
    EngineRun is the authoritative execution telemetry in WLJ.
    """
    try:
        from apps.core.ai_observability.models import EngineRun
        cutoff = timezone.now() - timedelta(hours=1)
        return EngineRun.objects.filter(
            started_at__gte=cutoff,
            status="error",
        ).count()
    except Exception as e:
        logger.debug("Celery health: failed task count failed: %s", e)
        return 0


def _classify_status(worker_count, queue_depth, failed_1h, broker_ok):
    """
    Classify overall Celery health.

    HEALTHY: workers running, queue manageable, failures minimal
    DEGRADED: workers missing, queue rising, moderate failures
    DOWN: no workers, queue stalled, or broker unreachable
    """
    if not broker_ok:
        return "DOWN"
    if worker_count == 0:
        return "DOWN"
    if queue_depth is not None and queue_depth >= QUEUE_DEPTH_CRITICAL:
        return "CRITICAL"
    if failed_1h >= FAILED_1H_CRITICAL:
        return "CRITICAL"
    if queue_depth is not None and queue_depth >= QUEUE_DEPTH_WARN:
        return "DEGRADED"
    if failed_1h >= FAILED_1H_WARN:
        return "DEGRADED"
    if worker_count < 2:
        return "DEGRADED"
    return "HEALTHY"


def get_celery_health():
    """
    Collect Celery execution layer health.

    Returns dict with:
        status: str — HEALTHY / DEGRADED / CRITICAL / DOWN
        worker_count: int — number of responsive workers
        workers: list — per-worker details
        queue_depth: int|None — messages waiting in queue
        active_tasks: int — tasks currently executing
        reserved_tasks: int — tasks prefetched by workers
        failed_1h: int — engine execution failures in last hour
        broker_connected: bool — whether Redis broker is reachable
    """
    app = _get_celery_app()
    if app is None:
        return {
            "status": "DOWN",
            "worker_count": 0,
            "workers": [],
            "queue_depth": None,
            "active_tasks": 0,
            "reserved_tasks": 0,
            "failed_1h": 0,
            "broker_connected": False,
        }

    # Collect all metrics
    queue_depth = _get_queue_depth()
    broker_connected = queue_depth is not None

    worker_data = _get_worker_stats(app)
    if worker_data is None:
        # Workers unreachable — still check if broker is up
        worker_data = {"workers": [], "active_tasks": 0, "reserved_tasks": 0}

    failed_1h = _get_failed_task_count_1h()
    worker_count = len(worker_data["workers"])

    status = _classify_status(worker_count, queue_depth, failed_1h, broker_connected)

    return {
        "status": status,
        "worker_count": worker_count,
        "workers": worker_data["workers"],
        "queue_depth": queue_depth if queue_depth is not None else 0,
        "active_tasks": worker_data["active_tasks"],
        "reserved_tasks": worker_data["reserved_tasks"],
        "failed_1h": failed_1h,
        "broker_connected": broker_connected,
    }
