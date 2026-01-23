# ==============================================================================
# File: apps/capture/jobs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Background job functions for capture audio expiration reminders
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-13
# Last Updated: 2026-01-13
# ==============================================================================
"""
Capture Background Jobs

Functions that are called by APScheduler for background processing.
These are referenced in config/wsgi.py and run periodically in production.

Jobs:
    - send_expiration_reminders: Send email reminders 2 days before audio expires
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.utils import user_log_id

logger = logging.getLogger(__name__)


def send_expiration_reminders():
    """
    Send reminder emails for capture entries whose audio expires in 2 days.

    This job runs daily to find entries where:
    - audio_expires_at is within 2 days from now
    - status is 'ready' (has audio to download)
    - reminder_sent_at is null (hasn't already received reminder)

    For each matching entry, it sends a reminder email to the user with
    a link to download the audio before it expires.

    Scheduled: Daily at 08:00 UTC (3:00 AM EST)
    """
    from apps.capture.models import CaptureEntry
    from apps.capture.services.expiration_reminder import send_expiration_reminder_email

    logger.info("Running audio expiration reminder job...")

    now = timezone.now()
    # Calculate the window: entries expiring between 1 and 2 days from now
    # This ensures we catch entries within the 2-day window but not those
    # already past the reminder point
    reminder_window_start = now + timedelta(days=1)
    reminder_window_end = now + timedelta(days=2)

    # Find entries that need reminders
    entries_needing_reminder = CaptureEntry.objects.filter(
        status=CaptureEntry.STATUS_READY,
        audio_expires_at__gte=reminder_window_start,
        audio_expires_at__lte=reminder_window_end,
        reminder_sent_at__isnull=True,
    ).select_related('user')

    sent_count = 0
    failed_count = 0

    for entry in entries_needing_reminder:
        try:
            result = send_expiration_reminder_email(entry)
            if result['success']:
                # Mark reminder as sent
                entry.reminder_sent_at = now
                entry.save(update_fields=['reminder_sent_at'])
                sent_count += 1
                logger.info(
                    f"Sent expiration reminder for entry {entry.id} "
                    f"to {user_log_id(entry.user)}"
                )
            else:
                failed_count += 1
                logger.warning(
                    f"Failed to send expiration reminder for entry {entry.id}: "
                    f"{result.get('error', 'Unknown error')}"
                )
        except Exception as e:
            failed_count += 1
            logger.exception(
                f"Error sending expiration reminder for entry {entry.id}: {e}"
            )

    if sent_count > 0 or failed_count > 0:
        logger.info(
            f"Expiration reminder job complete: {sent_count} sent, "
            f"{failed_count} failed"
        )
    else:
        logger.debug("No entries need expiration reminders")

    return {
        'sent': sent_count,
        'failed': failed_count,
        'checked': entries_needing_reminder.count() if hasattr(entries_needing_reminder, 'count') else sent_count + failed_count,
    }
