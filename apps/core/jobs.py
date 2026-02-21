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
    - compute_activity_patterns: Compute user activity patterns for personalized insights
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
        call_command('generate_health_reminders', '--medicine-only', '--time-period=morning', '--include-chat')
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
        call_command('generate_health_reminders', '--time-period=evening', '--include-chat')
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


def compute_activity_patterns():
    """
    Compute user activity patterns from daily interaction data.

    Analyzes UserDailyActivity records to determine each user's typical
    day start/end times. Results stored in UserActivityPattern and used
    by the AI insight system for personalized time-of-day messaging.

    Also cleans up activity records older than 90 days.

    Scheduled: Daily at 7:00 AM UTC (2:00 AM EST)
    """
    logger.info("Starting activity patterns computation job...")

    try:
        call_command('compute_activity_patterns', '--cleanup')
        logger.info("Activity patterns computation job completed successfully")
    except Exception as e:
        logger.exception(f"Activity patterns computation job failed: {e}")
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


def run_intelligence_scheduler():
    """
    Run one cycle of the Intelligence Scheduler Engine (ISE).

    Checks all registered intelligence tasks (DBE, GLOE, PGE) and
    executes any that are due. Each task tracks its own interval and
    last run time in the database.

    Scheduled: Every 5 minutes via APScheduler IntervalTrigger.
    """
    logger.info("Starting intelligence scheduler cycle...")

    try:
        from apps.core.ai_scheduler.scheduler_engine import run_scheduler_cycle

        result = run_scheduler_cycle()
        logger.info(
            f"Intelligence scheduler cycle completed: "
            f"executed={result['executed']}, "
            f"skipped={result['skipped']}, "
            f"failed={result['failed']}"
        )
    except Exception as e:
        logger.exception(f"Intelligence scheduler cycle failed: {e}")
        raise


def run_same_cycle():
    """
    Run one SAME (System Autonomous Monitoring Engine) cycle.

    Computes heartbeats, detects anomalies, generates narrative snapshot.
    Uses a database lock to prevent overlapping execution across workers.

    Scheduled: Every 60 seconds via APScheduler IntervalTrigger.
    """
    logger.info("SAME cycle starting...")

    # Concurrency guard — prevent overlapping SAME executions
    from apps.core.ai_scheduler.scheduler_models import SchedulerLock
    from django.utils import timezone as tz
    import os
    import socket

    lock_name = "same_execution"
    lock_timeout_seconds = 120  # 2 minutes — generous for a 60s cycle
    now = tz.now()
    locked_by = f"{socket.gethostname()}-{os.getpid()}"

    try:
        lock, created = SchedulerLock.objects.get_or_create(
            lock_name=lock_name,
            defaults={"locked_at": now, "locked_by": locked_by},
        )

        if not created:
            age = (now - lock.locked_at).total_seconds()
            if age < lock_timeout_seconds:
                logger.info(
                    f"SAME cycle skipped: lock held by {lock.locked_by} "
                    f"({age:.0f}s ago)"
                )
                return
            # Stale lock — take it over
            logger.warning(
                f"SAME cycle: taking over stale lock from {lock.locked_by} "
                f"({age:.0f}s old)"
            )
            lock.locked_at = now
            lock.locked_by = locked_by
            lock.save(update_fields=["locked_at", "locked_by"])

    except Exception as e:
        logger.warning(f"SAME cycle: lock check failed ({e}), proceeding anyway")

    try:
        from apps.core.ai_observability.same_engine import run_same

        result = run_same()
        logger.info(
            f"SAME cycle completed: "
            f"anomalies_created={result['anomalies_created']}, "
            f"anomalies_resolved={result['anomalies_resolved']}, "
            f"posture={result['narrative'].posture if result.get('narrative') else 'N/A'}"
        )
    except Exception as e:
        logger.exception(f"SAME cycle failed: {e}")
    finally:
        # Release lock
        try:
            SchedulerLock.objects.filter(
                lock_name=lock_name, locked_by=locked_by
            ).delete()
        except Exception:
            pass  # Best-effort release
