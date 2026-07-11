"""
WLJ Operations — recovery Celery task (Phase II).

``run_recovery_cycle_task`` is the SEPARATE, downstream task that the SAME cycle
hands off to (non-blocking ``safe_enqueue``) as its final step, ONLY when
``OPS_RECOVERY_ENABLED`` is True. It runs entirely in the worker — never on the
request path. A fault here can never delay/lengthen/destabilize the telemetry path,
which has already built and cached Operations Truth before this task is enqueued.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.core.operations.tasks.run_recovery_cycle_task",
    bind=True,
    max_retries=0,  # a missed recovery cycle is retried by the next SAME cycle
    ignore_result=True,
)
def run_recovery_cycle_task(self):
    """Run one deterministic recovery cycle, then publish read-only telemetry."""
    from django.conf import settings

    if not getattr(settings, "OPS_RECOVERY_ENABLED", False):
        return {"enabled": False}

    from apps.core.operations.recovery.engine import run_recovery_cycle
    from apps.core.operations.recovery.telemetry import publish_recovery_telemetry

    try:
        summary = run_recovery_cycle()
    except Exception:  # never swallow — log, still try to publish telemetry
        logger.error("Recovery cycle failed", exc_info=True)
        summary = {"enabled": True, "error": True}

    try:
        publish_recovery_telemetry()
    except Exception:  # pragma: no cover - telemetry is best-effort
        logger.error("Recovery telemetry publish failed", exc_info=True)

    logger.info("Recovery cycle complete: %s", summary)
    return summary
