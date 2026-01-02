# ==============================================================================
# File: apps/life/jobs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Life module scheduler job functions (must be importable by APScheduler)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-02
# ==============================================================================
"""
Life Module Jobs - Background job functions for APScheduler.

These functions are called by APScheduler using textual references
(e.g., 'apps.life.jobs:recalculate_task_priorities'). They must be importable
and cannot be nested/local functions.
"""

import logging

logger = logging.getLogger(__name__)


def recalculate_task_priorities():
    """
    Recalculate task priorities based on due dates.

    This job runs at 6:00 AM UTC (1:00 AM EST) to update task priorities so that
    tasks automatically move from "Soon" to "Now" as their due dates approach.

    Priority rules:
    - Now: Due today or overdue
    - Soon: Due within 7 days
    - Someday: Due more than 7 days away or no due date
    """
    from django.core.management import call_command
    from django.utils import timezone
    from io import StringIO

    current_time = timezone.now()
    logger.info(f"Starting task priority recalculation at {current_time} UTC")

    try:
        # Capture command output
        out = StringIO()
        call_command('recalculate_task_priorities', stdout=out, verbosity=2)
        output = out.getvalue().strip()

        logger.info(f"Task priority recalculation complete at {timezone.now()} UTC")
        logger.info(f"Result: {output}")
        return output
    except Exception as e:
        logger.exception(f"Error in task priority recalculation: {e}")
        return None


def process_recurring_tasks():
    """
    Process completed recurring tasks and create next occurrences.

    This job runs at 6:05 AM UTC (1:05 AM EST) to handle recurring tasks that
    were completed and need their next occurrence created.
    """
    from django.core.management import call_command
    from django.utils import timezone
    from io import StringIO

    current_time = timezone.now()
    logger.info(f"Starting recurring task processing at {current_time} UTC")

    try:
        out = StringIO()
        call_command('process_recurring_tasks', stdout=out, verbosity=2)
        output = out.getvalue().strip()

        logger.info(f"Recurring task processing complete at {timezone.now()} UTC")
        logger.info(f"Result: {output}")
        return output
    except Exception as e:
        logger.exception(f"Error in recurring task processing: {e}")
        return None
