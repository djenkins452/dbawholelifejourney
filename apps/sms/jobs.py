# ==============================================================================
# File: jobs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: SMS scheduler job functions (must be importable by APScheduler)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
SMS Jobs - Background job functions for APScheduler.

These functions are called by APScheduler using textual references
(e.g., 'apps.sms.jobs:send_pending_sms'). They must be importable
and cannot be nested/local functions.
"""

import logging

logger = logging.getLogger(__name__)


def schedule_daily_reminders():
    """
    Schedule SMS reminders for all users.

    This job runs daily at midnight to create SMSNotification records
    for the upcoming day's reminders.
    """
    from apps.sms.scheduler import SMSScheduler

    logger.info("Running daily SMS scheduling job...")
    try:
        scheduler = SMSScheduler()
        results = scheduler.schedule_for_all_users()
        logger.info(f"Daily SMS scheduling complete: {results}")
        return results
    except Exception as e:
        logger.exception(f"Error in daily SMS scheduling: {e}")
        return None


def send_pending_sms():
    """
    Send all pending SMS notifications that are due.

    This job runs every 5 minutes to send notifications
    whose scheduled_for time has passed.
    """
    from apps.sms.services import SMSNotificationService

    logger.info("Running pending SMS send job...")
    try:
        service = SMSNotificationService()
        results = service.send_pending_notifications()
        if results['sent'] > 0 or results['failed'] > 0:
            logger.info(f"SMS send complete: {results}")
        else:
            logger.debug("No pending SMS to send")
        return results
    except Exception as e:
        logger.exception(f"Error sending pending SMS: {e}")
        return None
