"""
Background task functions for capture processing.

This module provides task definitions for processing capture entries
asynchronously. Tasks can be run:
1. Immediately via process_capture_entry() for on-demand processing
2. Periodically via APScheduler for processing pending entries

The processing pipeline:
1. Transcribe audio using Whisper API (transcription service)
2. Summarize transcript using OpenAI API (summarization service)
3. Update entry status to 'ready' on success or 'failed' on error

Usage:
    from apps.capture.tasks import process_capture_entry

    # Process a single entry (can be called synchronously or scheduled)
    result = process_capture_entry(entry_id)

    if result['success']:
        print(f"Entry processed successfully")
    else:
        print(f"Processing failed: {result['error']}")
"""

import logging
from typing import Optional

from django.db import transaction

logger = logging.getLogger(__name__)

# Task settings
MAX_RETRIES = 3
TASK_TIMEOUT_SECONDS = 600  # 10 minutes


class CaptureProcessingError(Exception):
    """Exception raised during capture processing."""

    def __init__(self, message: str, user_message: str = None, retryable: bool = False):
        super().__init__(message)
        self.user_message = user_message or message
        self.retryable = retryable


def process_capture_entry(
    entry_id: str,
    retry_count: int = 0
) -> dict:
    """
    Process a single capture entry through the full pipeline.

    This is the main task function that orchestrates:
    1. Transcription via Whisper API
    2. Summarization via OpenAI API
    3. Status updates

    Args:
        entry_id: UUID string of the CaptureEntry to process
        retry_count: Current retry attempt (0 = first attempt)

    Returns:
        dict with keys:
            - success: bool
            - message: str
            - entry_id: str
            - retried: bool (if this was a retry)
            - should_retry: bool (if failed and should retry)
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
            'should_retry': False
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
            'should_retry': False
        }

    try:
        # Step 1: Transcription
        logger.info(f"Entry {entry_id}: Starting transcription")
        transcription_result = transcription_service.transcribe_audio(entry)

        if not transcription_result['success']:
            error_msg = transcription_result.get('error', 'Transcription failed')
            logger.error(f"Entry {entry_id}: Transcription failed - {error_msg}")

            # Check if should retry
            if _is_retryable_error(error_msg) and retry_count < MAX_RETRIES:
                return {
                    'success': False,
                    'message': f"Transcription failed: {error_msg}",
                    'entry_id': entry_id,
                    'retried': retry_count > 0,
                    'should_retry': True
                }

            # Entry status already set to failed by transcription service
            return {
                'success': False,
                'message': f"Transcription failed: {error_msg}",
                'entry_id': entry_id,
                'retried': retry_count > 0,
                'should_retry': False
            }

        # Step 2: Summarization
        # Reload entry to get updated transcript from transcription step
        entry.refresh_from_db()
        logger.info(f"Entry {entry_id}: Starting summarization")
        summarization_result = summarization_service.summarize_transcript(entry)

        if not summarization_result['success']:
            error_msg = summarization_result.get('error', 'Summarization failed')
            logger.error(f"Entry {entry_id}: Summarization failed - {error_msg}")

            # Check if should retry
            if _is_retryable_error(error_msg) and retry_count < MAX_RETRIES:
                # Reset status back to transcribing for retry
                entry.status = CaptureEntry.STATUS_TRANSCRIBING
                entry.save(update_fields=['status'])
                return {
                    'success': False,
                    'message': f"Summarization failed: {error_msg}",
                    'entry_id': entry_id,
                    'retried': retry_count > 0,
                    'should_retry': True
                }

            # Entry status already set to failed by summarization service
            return {
                'success': False,
                'message': f"Summarization failed: {error_msg}",
                'entry_id': entry_id,
                'retried': retry_count > 0,
                'should_retry': False
            }

        # Success! Entry status already set to 'ready' by summarization service
        logger.info(f"Entry {entry_id}: Processing complete")
        return {
            'success': True,
            'message': 'Processing complete',
            'entry_id': entry_id,
            'retried': retry_count > 0,
            'should_retry': False
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

        return {
            'success': False,
            'message': f"Unexpected error: {str(e)}",
            'entry_id': entry_id,
            'retried': retry_count > 0,
            'should_retry': retry_count < MAX_RETRIES
        }


def process_pending_captures() -> dict:
    """
    Process all capture entries that are pending transcription.

    This is a periodic task that can be scheduled via APScheduler
    to process any entries stuck in 'transcribing' status.

    Returns:
        dict with processing results:
            - processed: int (number of entries processed)
            - succeeded: int (number of successful completions)
            - failed: int (number of failures)
            - entries: list of entry_id results
    """
    from apps.capture.models import CaptureEntry

    logger.info("Running process_pending_captures job...")

    # Find all entries in 'transcribing' status
    pending_entries = CaptureEntry.objects.filter(
        status=CaptureEntry.STATUS_TRANSCRIBING
    ).order_by('created_at')

    results = {
        'processed': 0,
        'succeeded': 0,
        'failed': 0,
        'entries': []
    }

    for entry in pending_entries:
        results['processed'] += 1
        logger.info(f"Processing pending entry {entry.id}")

        result = process_capture_entry(str(entry.id))
        results['entries'].append(result)

        if result['success']:
            results['succeeded'] += 1
        else:
            results['failed'] += 1

            # Handle retry if needed
            if result.get('should_retry'):
                retry_result = _retry_with_backoff(str(entry.id), 1)
                if retry_result['success']:
                    results['failed'] -= 1
                    results['succeeded'] += 1

    if results['processed'] > 0:
        logger.info(
            f"Processed {results['processed']} pending captures: "
            f"{results['succeeded']} succeeded, {results['failed']} failed"
        )
    else:
        logger.debug("No pending captures to process")

    return results


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


def _retry_with_backoff(entry_id: str, retry_count: int) -> dict:
    """
    Retry processing with exponential backoff.

    Args:
        entry_id: UUID string of the entry to retry
        retry_count: Current retry number (1, 2, 3...)

    Returns:
        Result dict from process_capture_entry
    """
    import time

    # Calculate backoff delay: 2^retry_count seconds (2, 4, 8 seconds)
    delay = min(2 ** retry_count, 30)  # Cap at 30 seconds

    logger.info(f"Retrying entry {entry_id} in {delay} seconds (attempt {retry_count + 1}/{MAX_RETRIES})")
    time.sleep(delay)

    result = process_capture_entry(entry_id, retry_count=retry_count)

    # Continue retrying if needed
    if not result['success'] and result.get('should_retry') and retry_count < MAX_RETRIES:
        return _retry_with_backoff(entry_id, retry_count + 1)

    return result


def get_processing_queue_status() -> dict:
    """
    Get current status of the capture processing queue.

    Returns:
        dict with queue statistics
    """
    from datetime import timedelta

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
