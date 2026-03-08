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

# Module-level scheduler reference for health checks and restart.
# Accessed by apps.core.scheduler_health module.
_scheduler_instance = None

# Start background schedulers in production (only once, not in each worker)
# Protection layers:
#   1. DEBUG check (skip in dev)
#   2. os.environ['SCHEDULER_STARTED'] (in-process dedup with --preload)
#   3. Database lock (cross-process/container dedup via SchedulerLock)
def start_scheduler():
    """Start background schedulers if not already running."""
    import logging
    from django.conf import settings

    logger = logging.getLogger('scheduler')

    # EMERGENCY 2026-03-08: Scheduler disabled to stop DB connection saturation.
    # After downtime, all overdue jobs fire simultaneously, exhausting DB pool
    # and starving web requests (journal save 30s+, dashboard 524).
    # Re-enable once system is stable by removing this block.
    logger.warning("APScheduler DISABLED (emergency mode) — re-enable in wsgi.py when stable")
    return

    # Layer 1: Skip in development
    if settings.DEBUG:
        logger.info("Scheduler skipped: DEBUG mode is enabled")
        return

    # Layer 2: In-process dedup (Gunicorn --preload runs wsgi.py once before fork)
    if os.environ.get('SCHEDULER_STARTED'):
        logger.debug("Scheduler already started in this process")
        return

    # Layer 3: Database lock (cross-process/container singleton)
    try:
        from apps.core.ai_scheduler.scheduler_lock import acquire_scheduler_lock
        if not acquire_scheduler_lock():
            logger.info("Scheduler skipped: another instance holds the DB lock")
            return
    except Exception as e:
        # DB not ready (e.g., first deploy before migrate) — fall through
        logger.warning(f"Scheduler lock check failed ({e}), proceeding with env var guard")

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

        # =====================================================================
        # Core Jobs (CISO Review 2026-01-12)
        # =====================================================================

        # Job 5: Soft-delete cleanup weekly on Sunday at 3:00 AM UTC
        # Permanently deletes records that have been soft-deleted past retention period
        scheduler.add_job(
            'apps.core.jobs:cleanup_soft_deletes',
            trigger=CronTrigger(day_of_week='sun', hour=3, minute=0),
            id="cleanup_soft_deletes",
            max_instances=1,
            replace_existing=True,
        )

        # =====================================================================
        # Faith Module Jobs
        # =====================================================================

        # Job 7: Generate faith reminders at 6:00 AM UTC (1:00 AM EST)
        # Creates in-app/email notifications for prayers and reading plans
        scheduler.add_job(
            'apps.core.jobs:generate_faith_reminders',
            trigger=CronTrigger(hour=6, minute=0),
            id="generate_faith_reminders",
            max_instances=1,
            replace_existing=True,
        )

        # Job 9: Morning health reminders at 12:00 PM UTC (7:00 AM EST)
        # Creates medicine reminders for pending doses
        scheduler.add_job(
            'apps.core.jobs:generate_health_reminders_morning',
            trigger=CronTrigger(hour=12, minute=0),
            id="generate_health_reminders_morning",
            max_instances=1,
            replace_existing=True,
        )

        # Job 10: Evening health reminders at 12:00 AM UTC (7:00 PM EST)
        # Creates medicine, workout, and journal reminders
        scheduler.add_job(
            'apps.core.jobs:generate_health_reminders_evening',
            trigger=CronTrigger(hour=0, minute=0),
            id="generate_health_reminders_evening",
            max_instances=1,
            replace_existing=True,
        )

        # Job 11: Send daily digest emails at 9:45 AM UTC (4:45 AM EST)
        # Sends email digest to users with pending notifications
        scheduler.add_job(
            'apps.core.jobs:send_notification_digest',
            trigger=CronTrigger(hour=9, minute=45),
            id="send_notification_digest",
            max_instances=1,
            replace_existing=True,
        )

        # Job 12: Generate birthday/anniversary reminders at 12:00 PM UTC (7:00 AM EST)
        # Notifies users about birthdays, memorials, and anniversaries
        scheduler.add_job(
            'apps.core.jobs:generate_birthday_reminders',
            trigger=CronTrigger(hour=12, minute=0),
            id="generate_birthday_reminders",
            max_instances=1,
            replace_existing=True,
        )

        # =====================================================================
        # Activity Pattern Jobs
        # =====================================================================

        # Job 13: Compute user activity patterns at 7:00 AM UTC (2:00 AM EST)
        # Analyzes daily interaction data to personalize insight timing
        scheduler.add_job(
            'apps.core.jobs:compute_activity_patterns',
            trigger=CronTrigger(hour=7, minute=0),
            id="compute_activity_patterns",
            max_instances=1,
            replace_existing=True,
        )

        # =====================================================================
        # Capture Jobs
        # =====================================================================

        # Job 6: Send audio expiration reminder emails daily at 08:00 UTC (3:00 AM EST)
        # Notifies users when their audio files will expire in 2 days
        scheduler.add_job(
            'apps.capture.jobs:send_expiration_reminders',
            trigger=CronTrigger(hour=8, minute=0),
            id="send_expiration_reminders",
            max_instances=1,
            replace_existing=True,
        )

        # Job 8: Send pending capture reminder notifications hourly
        # Reminds users about recordings that haven't been uploaded
        scheduler.add_job(
            'apps.capture.jobs:send_pending_capture_reminders',
            trigger=IntervalTrigger(hours=1),
            id="send_pending_capture_reminders",
            max_instances=1,
            replace_existing=True,
        )

        # =====================================================================
        # Intelligence Scheduler (ISE)
        # =====================================================================

        # Job 14: Intelligence Scheduler Engine every 5 minutes
        # Orchestrates DBE (daily briefings), GLOE (learning profiles),
        # PGE (guidance refresh) based on each task's configured interval
        scheduler.add_job(
            'apps.core.jobs:run_intelligence_scheduler',
            trigger=IntervalTrigger(minutes=5),
            id="run_intelligence_scheduler",
            max_instances=1,
            replace_existing=True,
        )

        # Job 15: Refresh scheduler DB lock every 4 minutes
        # Keeps the singleton lock alive so stale detection works correctly
        scheduler.add_job(
            'apps.core.ai_scheduler.scheduler_lock:refresh_scheduler_lock',
            trigger=IntervalTrigger(minutes=4),
            id="refresh_scheduler_lock",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.start()

        # Store reference for health checks / restart via scheduler_health module
        global _scheduler_instance
        _scheduler_instance = scheduler

        logger.info("=" * 60)
        logger.info("APScheduler STARTED successfully with 15 jobs:")
        logger.info("  (SAME monitoring moved to Celery Beat)")
        logger.info("  - SMS: schedule_daily_sms_reminders (daily at 00:00 UTC) [on hold]")
        logger.info("  - SMS: send_pending_sms (every 5 minutes) [on hold]")
        logger.info("  - Life: recalculate_task_priorities (daily at 06:00 UTC / 01:00 EST)")
        logger.info("  - Life: process_recurring_tasks (daily at 06:05 UTC / 01:05 EST)")
        logger.info("  - Core: cleanup_soft_deletes (weekly on Sunday at 03:00 UTC)")
        logger.info("  - Core: generate_faith_reminders (daily at 06:00 UTC / 01:00 EST)")
        logger.info("  - Core: generate_health_reminders_morning (daily at 12:00 UTC / 07:00 EST)")
        logger.info("  - Core: generate_health_reminders_evening (daily at 00:00 UTC / 07:00 PM EST)")
        logger.info("  - Core: generate_birthday_reminders (daily at 12:00 UTC / 07:00 EST)")
        logger.info("  - Core: send_notification_digest (daily at 09:45 UTC / 04:45 EST)")
        logger.info("  - Core: compute_activity_patterns (daily at 07:00 UTC / 02:00 EST)")
        logger.info("  - Capture: send_expiration_reminders (daily at 08:00 UTC / 03:00 EST)")
        logger.info("  - Capture: send_pending_capture_reminders (hourly)")
        logger.info("  - ISE: run_intelligence_scheduler (every 5 minutes)")
        logger.info("  - ISE: refresh_scheduler_lock (every 4 minutes)")
        # SAME monitoring now handled by Celery Beat (run_same_cycle_task every 60s)
        logger.info("=" * 60)

        # Ensure scheduler shuts down on exit and releases DB lock
        def _shutdown_scheduler():
            scheduler.shutdown(wait=False)
            try:
                from apps.core.ai_scheduler.scheduler_lock import release_scheduler_lock
                release_scheduler_lock()
            except Exception:
                pass  # Best-effort — lock will expire naturally
        atexit.register(_shutdown_scheduler)

        # Run initial SMS send check
        from apps.sms.jobs import send_pending_sms
        send_pending_sms()

    except Exception as e:
        logger.exception(f"FAILED to start background scheduler: {e}")

# Start scheduler when WSGI app loads
start_scheduler()
