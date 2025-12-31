# ==============================================================================
# File: run_sms_scheduler.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to run the APScheduler for SMS notifications
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Run SMS Scheduler Management Command

Starts the APScheduler background scheduler that:
1. Schedules SMS reminders daily at midnight (for all users)
2. Sends pending SMS notifications every 5 minutes

This command should be run as a separate process in production.
It uses django-apscheduler to persist job state in the database.

Usage:
    python manage.py run_sms_scheduler
"""

import logging
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django.core.management.base import BaseCommand
from django_apscheduler import util
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

logger = logging.getLogger(__name__)


def schedule_daily_reminders():
    """
    Schedule SMS reminders for all users.

    This job runs daily at midnight (server time) to create
    SMSNotification records for the upcoming day.
    """
    from apps.sms.scheduler import SMSScheduler

    logger.info("Running daily SMS scheduling job...")
    try:
        scheduler = SMSScheduler()
        results = scheduler.schedule_for_all_users()
        logger.info(f"Daily SMS scheduling complete: {results}")
    except Exception as e:
        logger.exception(f"Error in daily SMS scheduling: {e}")


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
    except Exception as e:
        logger.exception(f"Error sending pending SMS: {e}")


@util.close_old_connections
def delete_old_job_executions(max_age=604800):
    """
    Delete APScheduler job execution logs older than max_age seconds.

    Default: 7 days (604800 seconds)
    This keeps the DjangoJobExecution table from growing too large.
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


class Command(BaseCommand):
    help = 'Run the SMS notification scheduler (APScheduler)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-schedule-job',
            action='store_true',
            help='Skip the daily scheduling job (useful for testing)',
        )
        parser.add_argument(
            '--no-send-job',
            action='store_true',
            help='Skip the send pending job (useful for testing)',
        )
        parser.add_argument(
            '--send-interval',
            type=int,
            default=5,
            help='Minutes between send pending checks (default: 5)',
        )
        parser.add_argument(
            '--schedule-hour',
            type=int,
            default=0,
            help='Hour to run daily scheduling (0-23, default: 0/midnight)',
        )

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        no_schedule = options['no_schedule_job']
        no_send = options['no_send_job']
        send_interval = options['send_interval']
        schedule_hour = options['schedule_hour']

        # Job 1: Daily scheduling at midnight (or configured hour)
        if not no_schedule:
            scheduler.add_job(
                schedule_daily_reminders,
                trigger=CronTrigger(hour=schedule_hour, minute=0),
                id="schedule_daily_sms_reminders",
                max_instances=1,
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Added job: schedule_daily_sms_reminders (runs at {schedule_hour}:00)")
            )

        # Job 2: Send pending SMS every N minutes
        if not no_send:
            scheduler.add_job(
                send_pending_sms,
                trigger=IntervalTrigger(minutes=send_interval),
                id="send_pending_sms",
                max_instances=1,
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Added job: send_pending_sms (every {send_interval} minutes)")
            )

        # Job 3: Clean up old job executions weekly
        scheduler.add_job(
            delete_old_job_executions,
            trigger=CronTrigger(day_of_week="sun", hour=0, minute=30),
            id="delete_old_job_executions",
            max_instances=1,
            replace_existing=True,
        )
        self.stdout.write(
            self.style.SUCCESS("Added job: delete_old_job_executions (weekly cleanup)")
        )

        try:
            self.stdout.write(self.style.SUCCESS("Starting SMS scheduler..."))
            logger.info("SMS scheduler starting...")
            scheduler.start()

            # Run an initial send check immediately on startup
            if not no_send:
                self.stdout.write("Running initial pending SMS check...")
                send_pending_sms()

            # Keep the main thread alive
            while True:
                time.sleep(60)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Scheduler interrupted, shutting down..."))
            scheduler.shutdown()
            self.stdout.write(self.style.SUCCESS("Scheduler stopped."))

        except Exception as e:
            logger.exception(f"Scheduler error: {e}")
            self.stderr.write(self.style.ERROR(f"Scheduler error: {e}"))
            scheduler.shutdown()
            sys.exit(1)
