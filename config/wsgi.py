"""
Whole Life Journey - WSGI Configuration

Project: Whole Life Journey
Path: config/wsgi.py
Purpose: WSGI entry point for production web server deployment

Description:
    This module provides the WSGI (Web Server Gateway Interface) application
    object that web servers like Gunicorn use to communicate with Django.
    It is the main entry point for production deployments on Railway.

Key Responsibilities:
    - Expose the WSGI application callable
    - Set the Django settings module environment variable
    - Initialize the Django application for request handling
    - Start background schedulers in production (non-DEBUG mode):
      - SMS scheduler for notifications
      - Life scheduler for task priority recalculation

Deployment:
    Used by Gunicorn in production via Procfile:
    web: gunicorn config.wsgi:application

For more information on WSGI deployment, see:
    https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import os
import atexit

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Start background schedulers in production (only once, not in each worker)
# We use an environment variable to ensure only one scheduler runs
def start_scheduler():
    """Start background schedulers if not already running."""
    import logging
    from django.conf import settings

    logger = logging.getLogger('scheduler')

    # Only run in production (non-DEBUG) and only if not already started
    if settings.DEBUG:
        logger.info("Scheduler skipped: DEBUG mode is enabled")
        return

    # Check if we're the main process (not a forked worker)
    # Gunicorn preload mode ensures this runs once before workers fork
    if os.environ.get('SCHEDULER_STARTED'):
        logger.debug("Scheduler already started in this process")
        return

    os.environ['SCHEDULER_STARTED'] = '1'
    logger.info("Initializing APScheduler background jobs...")

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        # Use MemoryJobStore instead of DjangoJobStore to avoid serialization issues
        # Jobs are re-registered on each startup anyway with replace_existing=True
        scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)

        # =====================================================================
        # SMS Jobs
        # =====================================================================

        # Job 1: Daily SMS scheduling at midnight
        scheduler.add_job(
            'apps.sms.jobs:schedule_daily_reminders',
            trigger=CronTrigger(hour=0, minute=0),
            id="schedule_daily_sms_reminders",
            max_instances=1,
            replace_existing=True,
        )

        # Job 2: Send pending SMS every 5 minutes
        scheduler.add_job(
            'apps.sms.jobs:send_pending_sms',
            trigger=IntervalTrigger(minutes=5),
            id="send_pending_sms",
            max_instances=1,
            replace_existing=True,
        )

        # =====================================================================
        # Life Module Jobs (Tasks)
        # =====================================================================

        # Job 3: Recalculate task priorities at 6:00 AM UTC (1:00 AM EST)
        # This ensures tasks update correctly for US Eastern timezone users.
        # Running at 1:00 AM EST gives time for the day to "turn over" in user's timezone
        # while still updating priorities early enough to be accurate all day.
        scheduler.add_job(
            'apps.life.jobs:recalculate_task_priorities',
            trigger=CronTrigger(hour=6, minute=0),
            id="recalculate_task_priorities",
            max_instances=1,
            replace_existing=True,
        )

        # Job 4: Process recurring tasks at 6:05 AM UTC (1:05 AM EST)
        scheduler.add_job(
            'apps.life.jobs:process_recurring_tasks',
            trigger=CronTrigger(hour=6, minute=5),
            id="process_recurring_tasks",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.start()
        logger.info("=" * 60)
        logger.info("APScheduler STARTED successfully with 4 jobs:")
        logger.info("  - SMS: schedule_daily_sms_reminders (daily at 00:00 UTC)")
        logger.info("  - SMS: send_pending_sms (every 5 minutes)")
        logger.info("  - Life: recalculate_task_priorities (daily at 06:00 UTC / 01:00 EST)")
        logger.info("  - Life: process_recurring_tasks (daily at 06:05 UTC / 01:05 EST)")
        logger.info("=" * 60)

        # Ensure scheduler shuts down on exit
        atexit.register(lambda: scheduler.shutdown(wait=False))

        # Run initial SMS send check
        from apps.sms.jobs import send_pending_sms
        send_pending_sms()

    except Exception as e:
        logger.exception(f"FAILED to start background scheduler: {e}")

# Start scheduler when WSGI app loads
start_scheduler()
