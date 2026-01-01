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
    - Start the SMS scheduler in production (non-DEBUG mode)

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

# Start SMS scheduler in production (only once, not in each worker)
# We use an environment variable to ensure only one scheduler runs
def start_scheduler():
    """Start the SMS background scheduler if not already running."""
    from django.conf import settings

    # Only run in production (non-DEBUG) and only if not already started
    if settings.DEBUG:
        return

    # Check if we're the main process (not a forked worker)
    # Gunicorn preload mode or single worker setup
    if os.environ.get('SMS_SCHEDULER_STARTED'):
        return

    os.environ['SMS_SCHEDULER_STARTED'] = '1'

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        from django_apscheduler.jobstores import DjangoJobStore
        import logging

        logger = logging.getLogger('apps.sms')

        scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # Import job functions
        from apps.sms.scheduler import SMSScheduler
        from apps.sms.services import SMSNotificationService

        def schedule_daily_reminders():
            """Schedule SMS reminders for all users."""
            try:
                sms_scheduler = SMSScheduler()
                results = sms_scheduler.schedule_for_all_users()
                logger.info(f"Daily SMS scheduling complete: {results}")
            except Exception as e:
                logger.exception(f"Error in daily SMS scheduling: {e}")

        def send_pending_sms():
            """Send all pending SMS notifications."""
            try:
                service = SMSNotificationService()
                results = service.send_pending_notifications()
                if results['sent'] > 0 or results['failed'] > 0:
                    logger.info(f"SMS send complete: {results}")
            except Exception as e:
                logger.exception(f"Error sending pending SMS: {e}")

        # Job 1: Daily scheduling at midnight
        scheduler.add_job(
            schedule_daily_reminders,
            trigger=CronTrigger(hour=0, minute=0),
            id="schedule_daily_sms_reminders",
            max_instances=1,
            replace_existing=True,
        )

        # Job 2: Send pending SMS every 5 minutes
        scheduler.add_job(
            send_pending_sms,
            trigger=IntervalTrigger(minutes=5),
            id="send_pending_sms",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.start()
        logger.info("SMS scheduler started successfully")

        # Ensure scheduler shuts down on exit
        atexit.register(lambda: scheduler.shutdown(wait=False))

        # Run initial send check
        send_pending_sms()

    except Exception as e:
        import logging
        logging.getLogger('apps.sms').exception(f"Failed to start SMS scheduler: {e}")

# Start scheduler when WSGI app loads
start_scheduler()
