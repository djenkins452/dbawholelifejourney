# ==============================================================================
# File: apps/life/jobs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Life module scheduler job functions (must be importable by APScheduler)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
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

    This job runs nightly at midnight to update task priorities so that
    tasks automatically move from "Soon" to "Now" as their due dates approach.

    Priority rules:
    - Now: Due today or overdue
    - Soon: Due within 7 days
    - Someday: Due more than 7 days away or no due date
    """
    from django.core.management import call_command
    from io import StringIO

    logger.info("Running nightly task priority recalculation...")
    try:
        # Capture command output
        out = StringIO()
        call_command('recalculate_task_priorities', stdout=out)
        output = out.getvalue().strip()

        logger.info(f"Task priority recalculation complete: {output}")
        return output
    except Exception as e:
        logger.exception(f"Error in task priority recalculation: {e}")
        return None


def process_recurring_tasks():
    """
    Process completed recurring tasks and create next occurrences.

    This job runs nightly to handle recurring tasks that were completed
    and need their next occurrence created.
    """
    from django.core.management import call_command
    from io import StringIO

    logger.info("Running nightly recurring task processing...")
    try:
        out = StringIO()
        call_command('process_recurring_tasks', stdout=out)
        output = out.getvalue().strip()

        logger.info(f"Recurring task processing complete: {output}")
        return output
    except Exception as e:
        logger.exception(f"Error in recurring task processing: {e}")
        return None
