"""
Celery tasks for capture processing.

This module provides Celery task definitions for processing capture entries
asynchronously. Tasks run on the Celery worker, surviving Gunicorn restarts.

The processing pipeline:
1. Transcribe audio using Whisper API (transcription service)
2. Summarize transcript using OpenAI API (summarization service)
3. Update entry status to 'ready' on success or 'failed' on error

Usage:
    from apps.capture.tasks import process_capture_entry

    # Dispatch to Celery worker (non-blocking)
    process_capture_entry.delay(str(entry.id))

    # Or call synchronously (e.g., in tests)
    result = process_capture_entry(str(entry.id))
"""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

# Task settings
MAX_RETRIES = 3


class CaptureProcessingError(Exception):
    """Exception raised during capture processing."""

    def __init__(self, message: str, user_message: str = None, retryable: bool = False):
        super().__init__(message)
        self.user_message = user_message or message
        self.retryable = retryable


@shared_task(
    name="capture.process_capture_entry",
    bind=True,
    max_retries=MAX_RETRIES,
    soft_time_limit=600,       # 10 minutes (transcription + summarization)
    time_limit=660,            # 11 minutes hard kill
    acks_late=True,
    default_retry_delay=30,
)
def process_capture_entry(
    self,
    entry_id: str,
    retry_count: int = 0
) -> dict:
    """
    Process a single capture entry through the full pipeline.

    This is the main Celery task that orchestrates:
    1. Transcription via Whisper API
    2. Summarization via OpenAI API
    3. Status updates

    Args:
        self: Celery task instance (bound task)
        entry_id: UUID string of the CaptureEntry to process
        retry_count: Current retry attempt (0 = first attempt)

    Returns:
        dict with keys:
            - success: bool
            - message: str
            - entry_id: str
            - retried: bool (if this was a retry)
    """
    from apps.capture.models import CaptureEntry
    from apps.capture.services import transcription_service, summarization_service

    logger.info(f"Processing capture entry {entry_id} (retry={retry_count})")

    # Fetch the entry
    try:
        entry = CaptureEntry.objects.get(id=entry_id)
    except CaptureEntry.DoesNotExist:
        logger.error(f"Capture entry {entry_id} not found")
        return {
            'success': False,
            'message': f"Entry {entry_id} not found",
            'entry_id': entry_id,
            'retried': retry_count > 0,
        }

    # Verify entry is in correct status (transcribing or failed with retries remaining)
    if entry.status not in [CaptureEntry.STATUS_TRANSCRIBING, CaptureEntry.STATUS_FAILED]:
        logger.warning(
            f"Entry {entry_id} has unexpected status '{entry.status}', expected 'transcribing' or 'failed'"
        )
        return {
            'success': False,
            'message': f"Entry not ready for processing (status: {entry.status})",
            'entry_id': entry_id,
            'retried': retry_count > 0,
        }

    try:
        # Step 1: Transcription
        logger.info(f"Entry {entry_id}: Starting transcription")
        transcription_result = transcription_service.transcribe_audio(entry)

        if not transcription_result['success']:
            error_msg = transcription_result.get('error', 'Transcription failed')
            logger.error(f"Entry {entry_id}: Transcription failed - {error_msg}")

            if _is_retryable_error(error_msg) and retry_count < MAX_RETRIES:
                backoff = min(2 ** (retry_count + 1), 30)
                logger.info(f"Entry {entry_id}: Scheduling retry in {backoff}s (attempt {retry_count + 1})")
                raise self.retry(
                    countdown=backoff,
                    kwargs={'entry_id': entry_id, 'retry_count': retry_count + 1},
                )

            # Non-retryable — entry status already set to failed by transcription service
            return {
                'success': False,
                'message': f"Transcription failed: {error_msg}",
                'entry_id': entry_id,
                'retried': retry_count > 0,
            }

        # Step 2: Summarization
        # Reload entry to get updated transcript from transcription step
        entry.refresh_from_db()
        logger.info(f"Entry {entry_id}: Starting summarization")
        summarization_result = summarization_service.summarize_transcript(entry)

        if not summarization_result['success']:
            error_msg = summarization_result.get('error', 'Summarization failed')
            logger.error(f"Entry {entry_id}: Summarization failed - {error_msg}")

            if _is_retryable_error(error_msg) and retry_count < MAX_RETRIES:
                # Reset status back to transcribing for retry
                entry.status = CaptureEntry.STATUS_TRANSCRIBING
                entry.save(update_fields=['status'])
                backoff = min(2 ** (retry_count + 1), 30)
                logger.info(f"Entry {entry_id}: Scheduling retry in {backoff}s (attempt {retry_count + 1})")
                raise self.retry(
                    countdown=backoff,
                    kwargs={'entry_id': entry_id, 'retry_count': retry_count + 1},
                )

            # Non-retryable — entry status already set to failed by summarization service
            return {
                'success': False,
                'message': f"Summarization failed: {error_msg}",
                'entry_id': entry_id,
                'retried': retry_count > 0,
            }

        # Success! Entry status already set to 'ready' by summarization service
        logger.info(f"Entry {entry_id}: Processing complete")

        # Send completion notification (in-app and email if user has them enabled)
        _send_completion_notification(entry, was_retry=retry_count > 0)

        # Update any associated PendingCapture record
        _complete_pending_capture(entry)

        return {
            'success': True,
            'message': 'Processing complete',
            'entry_id': entry_id,
            'retried': retry_count > 0,
        }

    except SoftTimeLimitExceeded:
        logger.error(f"Entry {entry_id}: Processing timed out (soft limit exceeded)")
        try:
            entry.status = CaptureEntry.STATUS_FAILED
            entry.error_message = "Processing timed out. Your recording may be too long. Please try again."
            entry.save(update_fields=['status', 'error_message'])
        except Exception:
            logger.error(f"Entry {entry_id}: Failed to update status after timeout")
        return {
            'success': False,
            'message': 'Processing timed out',
            'entry_id': entry_id,
            'retried': retry_count > 0,
        }

    except self.MaxRetriesExceededError:
        logger.error(f"Entry {entry_id}: Max retries exceeded")
        try:
            entry.status = CaptureEntry.STATUS_FAILED
            entry.error_message = "Processing failed after multiple attempts. Please try again later."
            entry.save(update_fields=['status', 'error_message'])
        except Exception:
            logger.error(f"Entry {entry_id}: Failed to update status after max retries")
        return {
            'success': False,
            'message': 'Max retries exceeded',
            'entry_id': entry_id,
            'retried': True,
        }

    except Exception as e:
        logger.exception(f"Entry {entry_id}: Unexpected error during processing")

        # Mark entry as failed
        try:
            entry.status = CaptureEntry.STATUS_FAILED
            entry.error_message = "An unexpected error occurred. Please try again."
            entry.save(update_fields=['status', 'error_message'])
        except Exception:
            logger.error(f"Entry {entry_id}: Failed to update status after error")

        # Retry if retryable
        if retry_count < MAX_RETRIES:
            backoff = min(2 ** (retry_count + 1), 30)
            try:
                raise self.retry(
                    countdown=backoff,
                    kwargs={'entry_id': entry_id, 'retry_count': retry_count + 1},
                    exc=e,
                )
            except self.MaxRetriesExceededError:
                pass

        return {
            'success': False,
            'message': f"Unexpected error: {str(e)}",
            'entry_id': entry_id,
            'retried': retry_count > 0,
        }


@shared_task(
    name="capture.process_pending_captures",
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def process_pending_captures() -> dict:
    """
    Find and dispatch processing for entries stuck in 'transcribing' status.

    This periodic task (Celery Beat, every 5 minutes) catches entries that
    were orphaned by previous daemon thread processing or worker crashes.
    Each entry is dispatched as a separate Celery task for parallel processing.

    Returns:
        dict with dispatch results:
            - dispatched: int (number of entries dispatched)
            - entry_ids: list of dispatched entry IDs
    """
    from apps.capture.models import CaptureEntry

    logger.info("Running process_pending_captures job...")

    # Find all entries stuck in 'transcribing' status
    pending_entries = CaptureEntry.objects.filter(
        status=CaptureEntry.STATUS_TRANSCRIBING
    ).order_by('created_at')

    dispatched = 0
    entry_ids = []

    for entry in pending_entries:
        logger.info(f"Dispatching stuck entry {entry.id} for processing")
        process_capture_entry.delay(str(entry.id))
        dispatched += 1
        entry_ids.append(str(entry.id))

    if dispatched > 0:
        logger.info(f"Dispatched {dispatched} stuck capture entries for processing")
    else:
        logger.debug("No stuck captures to process")

    return {
        'dispatched': dispatched,
        'entry_ids': entry_ids,
    }


def _is_retryable_error(error_msg: str) -> bool:
    """
    Determine if an error is transient and worth retrying.

    Args:
        error_msg: The error message string

    Returns:
        True if the error is likely transient and worth retrying
    """
    error_lower = error_msg.lower()

    # Retryable conditions
    retryable_keywords = [
        'rate_limit',
        'rate limit',
        'timeout',
        'timed out',
        'busy',
        'temporarily unavailable',
        'connection',
        'network',
        '503',
        '502',
        '429',
    ]

    for keyword in retryable_keywords:
        if keyword in error_lower:
            return True

    return False


def _send_completion_notification(entry, was_retry: bool = False) -> None:
    """
    Send completion notification when processing finishes.

    Sends both in-app notification (always) and email (if user has email
    capture notifications enabled).

    Args:
        entry: CaptureEntry instance that completed processing
        was_retry: Whether this was a delayed/retry processing
    """
    from apps.core.services.notification_service import NotificationService

    try:
        # Build notification context
        duration_text = ""
        if entry.duration_seconds:
            mins, secs = divmod(entry.duration_seconds, 60)
            if mins > 0:
                duration_text = f" ({mins}:{secs:02d})"
            else:
                duration_text = f" ({secs}s)"

        title = "Recording Ready"
        message = f"Your recording{duration_text} has been processed and is ready to view."

        # Send notification via unified notification service
        # This handles both in-app and email based on user preferences
        result = NotificationService.send(
            user=entry.user,
            category='capture',
            title=title,
            message=message,
            context={
                'entry_id': str(entry.id),
                'action_url': f'/capture/{entry.id}/',
                'action_label': 'View Recording',
                'was_retry': was_retry,
            },
        )

        if result.get('inapp') or result.get('email'):
            logger.info(f"Sent completion notification for entry {entry.id}")
        else:
            logger.debug(f"No notifications sent for entry {entry.id} (user disabled)")

    except Exception as e:
        logger.exception(f"Error sending completion notification for entry {entry.id}: {e}")


def _complete_pending_capture(entry) -> None:
    """
    Mark any associated PendingCapture record as completed.

    Args:
        entry: CaptureEntry instance that completed processing
    """
    if not entry.pending_client_id:
        return

    try:
        from apps.capture.models import PendingCapture

        pending = PendingCapture.objects.filter(
            user=entry.user,
            client_id=entry.pending_client_id,
        ).first()

        if pending:
            pending.status = PendingCapture.STATUS_COMPLETED
            pending.capture_entry = entry
            pending.save(update_fields=['status', 'capture_entry', 'updated_at'])
            logger.info(f"Marked PendingCapture {pending.id} as completed")

    except Exception as e:
        logger.warning(f"Failed to complete PendingCapture for entry {entry.id}: {e}")


def get_processing_queue_status() -> dict:
    """
    Get current status of the capture processing queue.

    Returns:
        dict with queue statistics
    """

    from django.utils import timezone

    from apps.capture.models import CaptureEntry

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    status = {
        'uploading': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_UPLOADING
        ).count(),
        'transcribing': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_TRANSCRIBING
        ).count(),
        'summarizing': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_SUMMARIZING
        ).count(),
        'ready': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_READY
        ).count(),
        'failed': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_FAILED
        ).count(),
        'completed_today': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_READY,
            updated_at__gte=today_start
        ).count(),
        'failed_today': CaptureEntry.objects.filter(
            status=CaptureEntry.STATUS_FAILED,
            updated_at__gte=today_start
        ).count(),
    }

    return status
