# ==============================================================================
# File: apps/core/jobs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Background job functions for the core module
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review)
# Last Updated: 2026-01-20
# ==============================================================================
"""
Core Background Jobs

Functions that are called by APScheduler for background processing.
These are referenced in config/wsgi.py and run periodically in production.

Jobs:
    - cleanup_soft_deletes: Permanently delete expired soft-deleted records
    - generate_faith_reminders: Create prayer and reading plan notifications
"""

import logging

from django.core.management import call_command

logger = logging.getLogger('scheduler')


def cleanup_soft_deletes():
    """
    Permanently delete records past the soft-delete retention period.

    This job calls the cleanup_soft_deletes management command which:
    - Finds all soft-deleted records older than the retention period
    - Permanently deletes them from the database
    - Logs all deletions for audit purposes

    Scheduled: Weekly on Sunday at 3:00 AM UTC
    """
    logger.info("Starting soft-delete cleanup job...")

    try:
        call_command('cleanup_soft_deletes')
        logger.info("Soft-delete cleanup job completed successfully")
    except Exception as e:
        logger.exception(f"Soft-delete cleanup job failed: {e}")
        # Re-raise to let the scheduler handle it
        raise


def generate_faith_reminders():
    """
    Generate in-app and email notifications for faith module reminders.

    Creates notifications for:
    - Prayer requests with remind_daily=True
    - Active reading plans not yet completed today

    Scheduled: Daily at 6:00 AM UTC (1:00 AM EST)
    """
    logger.info("Starting faith reminders job...")

    try:
        call_command('generate_daily_reminders')
        logger.info("Faith reminders job completed successfully")
    except Exception as e:
        logger.exception(f"Faith reminders job failed: {e}")
        raise


def generate_health_reminders_morning():
    """
    Generate morning health reminders (medicine only).

    Creates notifications for:
    - Medicine doses scheduled for today that haven't been taken

    Scheduled: Daily at 12:00 PM UTC (7:00 AM EST)
    """
    logger.info("Starting morning health reminders job...")

    try:
        call_command('generate_health_reminders', '--medicine-only', '--time-period=morning')
        logger.info("Morning health reminders job completed successfully")
    except Exception as e:
        logger.exception(f"Morning health reminders job failed: {e}")
        raise


def generate_health_reminders_evening():
    """
    Generate evening health reminders (medicine, workout, journal).

    Creates notifications for:
    - Medicine doses scheduled for today that haven't been taken
    - Users who haven't logged a workout today
    - Users who haven't journaled today

    Scheduled: Daily at 12:00 AM UTC (7:00 PM EST)
    """
    logger.info("Starting evening health reminders job...")

    try:
        call_command('generate_health_reminders', '--time-period=evening')
        logger.info("Evening health reminders job completed successfully")
    except Exception as e:
        logger.exception(f"Evening health reminders job failed: {e}")
        raise


def send_notification_digest():
    """
    Send daily email digest of pending notifications to users.

    Sends a single email summarizing all pending notifications for users
    who have 'daily_digest' email frequency selected.

    Scheduled: Daily at 9:45 AM UTC (4:45 AM EST)
    """
    logger.info("Starting notification digest job...")

    try:
        call_command('send_notification_digest')
        logger.info("Notification digest job completed successfully")
    except Exception as e:
        logger.exception(f"Notification digest job failed: {e}")
        raise


def generate_birthday_reminders():
    """
    Generate birthday and memorial reminder notifications.

    Creates notifications for:
    - Pet birthdays (living pets)
    - Pet memorials (passed pets)
    - People birthdays and anniversaries (via SignificantEvent)

    Scheduled: Daily at 12:00 PM UTC (7:00 AM EST)
    """
    logger.info("Starting birthday reminders job...")

    try:
        call_command('generate_birthday_reminders')
        logger.info("Birthday reminders job completed successfully")
    except Exception as e:
        logger.exception(f"Birthday reminders job failed: {e}")
        raise
