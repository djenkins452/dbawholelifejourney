"""
Celery tasks for Meal Intelligence async processing.

Currently handles pantry photo scan processing through Vision AI.
"""

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.meals.tasks.process_pantry_scan_task",
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=180,  # 3 minutes — generous for 5 photos
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_pantry_scan_task(self, session_id):
    """
    Process all unprocessed uploads in a pantry scan session through Vision AI.

    Called async from PantryScanStartView after images are saved.
    The confirm page polls for completion.

    Args:
        session_id: PK of PantryScanSession to process
    """
    from apps.meals.models import PantryScanSession
    from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

    task_id = self.request.id or "local"
    start = time.monotonic()

    logger.info(
        "Pantry scan task starting (session=%d, task_id=%s)",
        session_id, task_id,
    )

    try:
        session = PantryScanSession.objects.get(pk=session_id)
    except PantryScanSession.DoesNotExist:
        logger.error("Pantry scan session %d not found", session_id)
        return {"status": "error", "reason": "session_not_found"}

    unprocessed = list(session.uploads.filter(processed=False))
    processed_count = 0
    error_count = 0

    try:
        for upload in unprocessed:
            try:
                pantry_photo_detection_service.process_upload(upload)
                processed_count += 1
            except Exception as e:
                logger.error(
                    "Failed to process upload %d in session %d: %s",
                    upload.pk, session_id, e, exc_info=True,
                )
                # Mark as processed with error so we don't retry forever
                upload.processed = True
                upload.raw_detection_json = {"error": str(e)}
                upload.save(update_fields=["processed", "raw_detection_json"])
                error_count += 1

    except SoftTimeLimitExceeded:
        logger.warning(
            "Pantry scan task timed out (session=%d, processed=%d/%d)",
            session_id, processed_count, len(unprocessed),
        )
        # Mark remaining uploads as processed with timeout error
        for upload in session.uploads.filter(processed=False):
            upload.processed = True
            upload.raw_detection_json = {"error": "Processing timed out"}
            upload.save(update_fields=["processed", "raw_detection_json"])
        return {
            "status": "timeout",
            "session_id": session_id,
            "processed": processed_count,
            "total": len(unprocessed),
        }

    duration = time.monotonic() - start
    logger.info(
        "Pantry scan task complete (session=%d, processed=%d, errors=%d, %.1fs)",
        session_id, processed_count, error_count, duration,
    )

    return {
        "status": "ok",
        "session_id": session_id,
        "processed": processed_count,
        "errors": error_count,
        "duration_seconds": round(duration, 2),
    }
