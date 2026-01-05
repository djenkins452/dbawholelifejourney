"""
Run Improvement Scheduler Management Command.

Owner: admin@wholelifejourney.com

Starts the APScheduler background scheduler that:
1. Processes approved improvement tasks every 5 minutes
2. Processes autonomous (low-severity) tasks every 5 minutes
3. Monitors for stuck tasks every 10 minutes

This command should be run as a separate process in production.
It uses django-apscheduler to persist job state in the database.

Usage:
    python manage.py run_improvement_scheduler
"""

import logging
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django.core.management.base import BaseCommand
from django_apscheduler import util
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

logger = logging.getLogger(__name__)


def process_approved_tasks_job():
    """
    Scheduled job to process approved improvement tasks.

    This job runs every 5 minutes to execute tasks that have been
    approved by admin.
    """
    from assistant.tasks import process_approved_tasks

    logger.info("Running approved tasks processing job...")
    try:
        results = process_approved_tasks()
        if results['processed'] > 0:
            logger.info(f"Approved tasks job complete: {results}")
    except Exception as e:
        logger.exception(f"Error in approved tasks job: {e}")


def process_autonomous_tasks_job():
    """
    Scheduled job to process autonomous improvement tasks.

    This job runs every 5 minutes to execute low-severity tasks
    that don't require admin approval.
    """
    from assistant.tasks import process_autonomous_tasks

    logger.info("Running autonomous tasks processing job...")
    try:
        results = process_autonomous_tasks()
        if results['processed'] > 0:
            logger.info(f"Autonomous tasks job complete: {results}")
    except Exception as e:
        logger.exception(f"Error in autonomous tasks job: {e}")


def monitor_stuck_tasks_job():
    """
    Scheduled job to monitor for stuck tasks.

    This job runs every 10 minutes to detect tasks that have been
    IN_PROGRESS for too long and alert the admin.
    """
    from assistant.tasks import monitor_stuck_tasks

    logger.info("Running stuck task monitor job...")
    try:
        results = monitor_stuck_tasks()
        if results['stuck_count'] > 0:
            logger.warning(f"Stuck task monitor found issues: {results}")
    except Exception as e:
        logger.exception(f"Error in stuck task monitor: {e}")


@util.close_old_connections
def delete_old_job_executions(max_age=604800):
    """
    Delete APScheduler job execution logs older than max_age seconds.

    Default: 7 days (604800 seconds)
    This keeps the DjangoJobExecution table from growing too large.
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


class Command(BaseCommand):
    help = 'Run the improvement task scheduler (APScheduler)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-approved-job',
            action='store_true',
            help='Skip the approved tasks processing job',
        )
        parser.add_argument(
            '--no-autonomous-job',
            action='store_true',
            help='Skip the autonomous tasks processing job',
        )
        parser.add_argument(
            '--no-monitor-job',
            action='store_true',
            help='Skip the stuck task monitor job',
        )
        parser.add_argument(
            '--process-interval',
            type=int,
            default=5,
            help='Minutes between task processing checks (default: 5)',
        )
        parser.add_argument(
            '--monitor-interval',
            type=int,
            default=10,
            help='Minutes between stuck task checks (default: 10)',
        )

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        no_approved = options['no_approved_job']
        no_autonomous = options['no_autonomous_job']
        no_monitor = options['no_monitor_job']
        process_interval = options['process_interval']
        monitor_interval = options['monitor_interval']

        # Job 1: Process approved tasks every N minutes
        if not no_approved:
            scheduler.add_job(
                process_approved_tasks_job,
                trigger=IntervalTrigger(minutes=process_interval),
                id="process_approved_improvement_tasks",
                max_instances=1,
                replace_existing=True,
                misfire_grace_time=60,  # Allow 60s misfire window
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Added job: process_approved_improvement_tasks (every {process_interval} minutes)"
                )
            )

        # Job 2: Process autonomous tasks every N minutes
        if not no_autonomous:
            scheduler.add_job(
                process_autonomous_tasks_job,
                trigger=IntervalTrigger(minutes=process_interval),
                id="process_autonomous_improvement_tasks",
                max_instances=1,
                replace_existing=True,
                misfire_grace_time=60,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Added job: process_autonomous_improvement_tasks (every {process_interval} minutes)"
                )
            )

        # Job 3: Monitor for stuck tasks
        if not no_monitor:
            scheduler.add_job(
                monitor_stuck_tasks_job,
                trigger=IntervalTrigger(minutes=monitor_interval),
                id="monitor_stuck_improvement_tasks",
                max_instances=1,
                replace_existing=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Added job: monitor_stuck_improvement_tasks (every {monitor_interval} minutes)"
                )
            )

        # Job 4: Clean up old job executions weekly
        scheduler.add_job(
            delete_old_job_executions,
            trigger=IntervalTrigger(days=7),
            id="delete_old_improvement_job_executions",
            max_instances=1,
            replace_existing=True,
        )
        self.stdout.write(
            self.style.SUCCESS("Added job: delete_old_improvement_job_executions (weekly cleanup)")
        )

        try:
            self.stdout.write(self.style.SUCCESS("Starting improvement task scheduler..."))
            logger.info("Improvement task scheduler starting...")
            scheduler.start()

            # Run initial checks immediately on startup
            if not no_approved:
                self.stdout.write("Running initial approved tasks check...")
                process_approved_tasks_job()

            if not no_autonomous:
                self.stdout.write("Running initial autonomous tasks check...")
                process_autonomous_tasks_job()

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
