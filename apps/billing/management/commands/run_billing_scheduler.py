"""
Run Billing Scheduler Management Command

Starts the APScheduler background scheduler that:
1. Runs birthday processing daily at 3am
2. Runs monthly referral qualification checks on the 1st
3. Runs quarterly bonus processing on Jan 1, Apr 1, Jul 1, Oct 1

This command should be run as a separate process in production.
It uses django-apscheduler to persist job state in the database.

Usage:
    python manage.py run_billing_scheduler
"""

import logging
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_apscheduler import util
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

logger = logging.getLogger(__name__)


def run_birthday_processing():
    """
    Run the birthday processing command.

    This job runs daily at 3am to:
    - Send preview emails 30 days before 23rd birthday
    - Process users turning 23 today (set graduation date)
    - Send graduation reminders 30 days before
    - Process graduations (student -> adult)
    """
    logger.info("Running daily birthday processing job...")
    try:
        call_command('process_birthdays')
        logger.info("Birthday processing complete")
    except Exception as e:
        logger.exception(f"Error in birthday processing: {e}")


def run_monthly_qualification_check():
    """
    Run monthly check for referral qualifications.

    This job runs on the 1st of each month to check
    referrals hitting their 90-day qualification mark.
    """
    logger.info("Running monthly referral qualification check...")
    try:
        # The quarterly bonus command includes qualification updates
        call_command('process_quarterly_bonuses', dry_run=False)
        logger.info("Monthly qualification check complete")
    except Exception as e:
        logger.exception(f"Error in qualification check: {e}")


def run_quarterly_bonus_processing():
    """
    Run quarterly bonus calculation for Founding Members.

    This job runs on Jan 1, Apr 1, Jul 1, Oct 1 at 6am
    to calculate and create payout records.
    """
    logger.info("Running quarterly bonus processing...")
    try:
        call_command('process_quarterly_bonuses')
        logger.info("Quarterly bonus processing complete")
    except Exception as e:
        logger.exception(f"Error in quarterly bonus processing: {e}")


@util.close_old_connections
def delete_old_job_executions(max_age=604800):
    """
    Delete APScheduler job execution logs older than max_age seconds.

    Default: 7 days (604800 seconds)
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


class Command(BaseCommand):
    help = 'Run the billing scheduler (APScheduler) for birthdays, graduations, and bonuses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-birthday-job',
            action='store_true',
            help='Skip the daily birthday processing job',
        )
        parser.add_argument(
            '--no-monthly-job',
            action='store_true',
            help='Skip the monthly qualification check job',
        )
        parser.add_argument(
            '--no-quarterly-job',
            action='store_true',
            help='Skip the quarterly bonus job',
        )
        parser.add_argument(
            '--birthday-hour',
            type=int,
            default=3,
            help='Hour to run birthday processing (0-23, default: 3)',
        )

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        no_birthday = options['no_birthday_job']
        no_monthly = options['no_monthly_job']
        no_quarterly = options['no_quarterly_job']
        birthday_hour = options['birthday_hour']

        # Job 1: Daily birthday processing at 3am
        if not no_birthday:
            scheduler.add_job(
                run_birthday_processing,
                trigger=CronTrigger(hour=birthday_hour, minute=0),
                id="billing_birthday_processing",
                max_instances=1,
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Added job: billing_birthday_processing (daily at {birthday_hour}:00)")
            )

        # Job 2: Monthly qualification check on the 1st at 7am
        if not no_monthly:
            scheduler.add_job(
                run_monthly_qualification_check,
                trigger=CronTrigger(day=1, hour=7, minute=0),
                id="billing_monthly_qualification",
                max_instances=1,
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS("Added job: billing_monthly_qualification (1st of month at 7:00)")
            )

        # Job 3: Quarterly bonus processing on Jan/Apr/Jul/Oct 1 at 6am
        if not no_quarterly:
            scheduler.add_job(
                run_quarterly_bonus_processing,
                trigger=CronTrigger(month='1,4,7,10', day=1, hour=6, minute=0),
                id="billing_quarterly_bonus",
                max_instances=1,
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS("Added job: billing_quarterly_bonus (quarterly at 6:00)")
            )

        # Job 4: Clean up old job executions weekly
        scheduler.add_job(
            delete_old_job_executions,
            trigger=CronTrigger(day_of_week="sun", hour=1, minute=0),
            id="billing_delete_old_executions",
            max_instances=1,
            replace_existing=True,
        )
        self.stdout.write(
            self.style.SUCCESS("Added job: billing_delete_old_executions (weekly cleanup)")
        )

        try:
            self.stdout.write(self.style.SUCCESS("Starting billing scheduler..."))
            logger.info("Billing scheduler starting...")
            scheduler.start()

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
