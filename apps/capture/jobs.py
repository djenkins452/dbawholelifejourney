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

from django.db import models
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


def send_pending_capture_reminders():
    """
    Send reminder notifications for pending captures that haven't been uploaded.

    This job runs hourly to find pending captures that:
    - Are older than 1 hour
    - Haven't had a reminder sent today
    - Are in status 'pending', 'uploading', or 'downloaded'

    For each matching pending capture, it sends an in-app notification
    to remind the user to upload their recording.

    Scheduled: Hourly
    """
    from apps.capture.models import PendingCapture
    from apps.core.services.notification_service import NotificationService

    logger.info("Running pending capture reminder job...")

    now = timezone.now()
    one_hour_ago = now - timedelta(hours=1)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Find pending captures that need reminders
    pending_needing_reminder = PendingCapture.objects.filter(
        status__in=[
            PendingCapture.STATUS_PENDING,
            PendingCapture.STATUS_UPLOADING,
            PendingCapture.STATUS_DOWNLOADED,
        ],
        created_at__lte=one_hour_ago,
    ).filter(
        # No reminder sent today
        models.Q(last_reminder_at__isnull=True) |
        models.Q(last_reminder_at__lt=today_start)
    ).select_related('user')

    sent_count = 0
    failed_count = 0

    for pending in pending_needing_reminder:
        try:
            # Check if user has in-app capture notifications enabled
            prefs = pending.user.preferences
            if not getattr(prefs, 'notify_inapp_capture', True):
                continue

            # Calculate age for friendly message
            age_hours = int((now - pending.created_at).total_seconds() / 3600)
            if age_hours < 24:
                age_text = f"{age_hours} hour{'s' if age_hours != 1 else ''}"
            else:
                age_days = age_hours // 24
                age_text = f"{age_days} day{'s' if age_days != 1 else ''}"

            # Send in-app notification
            result = NotificationService.send(
                user=pending.user,
                category='capture',
                title='Recording Waiting to Upload',
                message=(
                    f"You have a recording from {age_text} ago that hasn't "
                    f"been uploaded yet. Open the Capture page to upload it."
                ),
                context={
                    'pending_id': str(pending.id),
                    'action_url': '/capture/record/',
                    'action_label': 'Upload Now',
                },
            )

            if result.get('inapp'):
                # Update last reminder timestamp
                pending.last_reminder_at = now
                pending.save(update_fields=['last_reminder_at'])
                sent_count += 1
                logger.info(
                    f"Sent pending capture reminder for {pending.id} "
                    f"to {pending.user.email}"
                )
            else:
                # Notification not sent (likely disabled)
                pass

        except Exception as e:
            failed_count += 1
            logger.exception(
                f"Error sending pending capture reminder for {pending.id}: {e}"
            )

    if sent_count > 0 or failed_count > 0:
        logger.info(
            f"Pending capture reminder job complete: {sent_count} sent, "
            f"{failed_count} failed"
        )
    else:
        logger.debug("No pending captures need reminders")

    return {
        'sent': sent_count,
        'failed': failed_count,
    }
