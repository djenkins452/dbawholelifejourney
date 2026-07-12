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
    from apps.core.operations.recovery.mode import DISABLED, get_recovery_mode

    if get_recovery_mode() == DISABLED:
        return {"enabled": False, "mode": DISABLED}

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


@shared_task(
    name="apps.core.operations.tasks.publish_recovery_telemetry_task",
    bind=True,
    max_retries=0,
    ignore_result=True,
)
def publish_recovery_telemetry_task(self):
    """Publish read-only recovery telemetry EVERY SAME cycle, regardless of mode.

    Recovery VISIBILITY must not depend on recovery being enabled: an operator needs
    to see mode, configured/enabled handlers, allowlists and status precisely when
    recovery is DISABLED. This is a read-only cache publish (a few count queries +
    config reads) — it takes NO recovery action and is separate from the mode-gated
    ``run_recovery_cycle_task``. Runs in the worker, never on the request path.
    """
    from apps.core.operations.recovery.telemetry import publish_recovery_telemetry

    try:
        publish_recovery_telemetry()
    except Exception:  # pragma: no cover - telemetry is best-effort
        logger.error("Recovery telemetry publish (standalone) failed", exc_info=True)
    return {"published": True}
