"""
Celery tasks for Life module async processing.

Handles bulk recipe photo import through Vision AI and
nightly task priority recalculation.
"""

import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


@shared_task(name="life.recalculate_task_priorities")
def recalculate_task_priorities_task():
    """Nightly task to recalculate priorities so tasks move Now/Soon/Someday."""
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_command('recalculate_task_priorities', stdout=out, verbosity=2)
    result = out.getvalue().strip()
    logger.info("Task priority recalculation: %s", result)
    return result


@shared_task(
    bind=True,
    name="apps.life.tasks.process_bulk_recipe_import",
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=1800,  # 30 minutes — generous for ~40 photos
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_bulk_recipe_import(self, session_id):
    """
    Process all pending photos in a bulk recipe import session.

    For each photo:
    1. Read image bytes from storage
    2. Call recipe_photo_import_service.extract_from_bytes()
    3. Store extracted recipe JSON on the photo record
    4. Update session progress counters

    Includes 2-second delay between API calls to avoid rate limiting.
    """
    from apps.life.models import RecipeBulkImportSession
    from apps.life.services.recipe_photo_import import recipe_photo_import_service

    task_id = self.request.id or "local"
    start = time.monotonic()

    logger.info(
        "Bulk recipe import starting (session=%d, task_id=%s)",
        session_id, task_id,
    )

    try:
        session = RecipeBulkImportSession.objects.get(pk=session_id)
    except RecipeBulkImportSession.DoesNotExist:
        logger.error("Bulk recipe import session %d not found", session_id)
        return {"status": "error", "reason": "session_not_found"}

    session.import_status = 'processing'
    session.celery_task_id = task_id
    session.save(update_fields=['import_status', 'celery_task_id', 'updated_at'])

    pending_photos = list(session.photos.filter(photo_status='pending'))
    processed_count = 0
    error_count = 0

    try:
        for i, photo in enumerate(pending_photos):
            # Mark as processing
            photo.photo_status = 'processing'
            photo.save(update_fields=['photo_status', 'updated_at'])

            try:
                # Read image bytes — try multiple strategies for storage backend
                # compatibility. The web process uses Cloudinary but the Celery
                # worker may fall back to FileSystemStorage if Cloudinary env
                # vars aren't configured, causing path mismatches.
                raw_bytes = None

                # Strategy 1: standard storage open (works when storage matches)
                try:
                    photo.image.open('rb')
                    raw_bytes = photo.image.read()
                    photo.image.close()
                except (FileNotFoundError, OSError):
                    pass

                # Strategy 2: fetch from Cloudinary URL stored at upload time
                if raw_bytes is None and photo.image_url:
                    import urllib.request
                    raw_bytes = urllib.request.urlopen(photo.image_url).read()

                # Strategy 3: try image.url (may work if storage is configured)
                if raw_bytes is None:
                    url = photo.image.url
                    if url.startswith('http'):
                        import urllib.request
                        raw_bytes = urllib.request.urlopen(url).read()

                if raw_bytes is None:
                    raise FileNotFoundError(
                        f"Could not read image for photo {photo.pk} "
                        f"(name={photo.image.name}, url={photo.image_url})"
                    )

                # Determine content type from extension
                name = (photo.original_filename or photo.image.name).lower()
                if name.endswith('.png'):
                    content_type = 'image/png'
                elif name.endswith('.webp'):
                    content_type = 'image/webp'
                elif name.endswith('.heic'):
                    content_type = 'image/heic'
                else:
                    content_type = 'image/jpeg'

                result = recipe_photo_import_service.extract_from_bytes(
                    raw_bytes, content_type
                )

                # Service returns list of recipes or dict with error
                if isinstance(result, dict) and "error" in result:
                    photo.photo_status = 'failed'
                    photo.error_message = result["error"]
                    photo.save(update_fields=[
                        'photo_status', 'error_message', 'updated_at',
                    ])
                    error_count += 1
                elif isinstance(result, list) and len(result) > 0:
                    # First recipe on this photo
                    photo.photo_status = 'extracted'
                    photo.extracted_data = result[0]
                    photo.confidence = result[0].get('confidence', 0.5)
                    photo.save(update_fields=[
                        'photo_status', 'extracted_data', 'confidence', 'updated_at',
                    ])
                    processed_count += 1

                    # Additional recipes → create new photo entries
                    from apps.life.models import RecipeBulkImportPhoto
                    for extra in result[1:]:
                        RecipeBulkImportPhoto.objects.create(
                            user=session.user,
                            session=session,
                            image=photo.image,
                            image_url=photo.image_url,
                            original_filename=photo.original_filename,
                            photo_status='extracted',
                            extracted_data=extra,
                            confidence=extra.get('confidence', 0.5),
                        )
                        processed_count += 1
                    if len(result) > 1:
                        session.total_photos = session.photos.count()
                else:
                    photo.photo_status = 'failed'
                    photo.error_message = 'No recipes found in image'
                    photo.save(update_fields=[
                        'photo_status', 'error_message', 'updated_at',
                    ])
                    error_count += 1

            except Exception as e:
                logger.error(
                    "Failed to process bulk import photo %d in session %d: %s",
                    photo.pk, session_id, e, exc_info=True,
                )
                photo.photo_status = 'failed'
                photo.error_message = str(e)
                photo.save(update_fields=['photo_status', 'error_message', 'updated_at'])
                error_count += 1

            # Update session progress
            session.processed_count = processed_count
            session.failed_count = error_count
            session.save(update_fields=[
                'processed_count', 'failed_count', 'updated_at',
            ])

            # Rate-limit delay between API calls (skip after last photo)
            if i < len(pending_photos) - 1:
                time.sleep(2)

    except SoftTimeLimitExceeded:
        logger.warning(
            "Bulk recipe import timed out (session=%d, processed=%d/%d)",
            session_id, processed_count, len(pending_photos),
        )
        # Mark remaining pending photos as failed
        session.photos.filter(photo_status__in=['pending', 'processing']).update(
            photo_status='failed',
            error_message='Processing timed out',
        )
        remaining = session.photos.filter(
            photo_status='failed', error_message='Processing timed out'
        ).count()
        session.failed_count = error_count + remaining
        session.import_status = 'completed'
        session.save(update_fields=['failed_count', 'import_status', 'updated_at'])
        return {
            "status": "timeout",
            "session_id": session_id,
            "processed": processed_count,
            "total": len(pending_photos),
        }

    # Mark session completed
    session.import_status = 'completed'
    session.save(update_fields=['import_status', 'updated_at'])

    duration = time.monotonic() - start
    logger.info(
        "Bulk recipe import complete (session=%d, processed=%d, errors=%d, %.1fs)",
        session_id, processed_count, error_count, duration,
    )

    return {
        "status": "ok",
        "session_id": session_id,
        "processed": processed_count,
        "errors": error_count,
        "duration_seconds": round(duration, 2),
    }
