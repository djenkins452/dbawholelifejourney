# ==============================================================================
# File: apps/life/management/commands/process_recurring_tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to process recurring tasks (scheduled job)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-03
# ==============================================================================
"""
Management command to process recurring tasks.

Run daily via cron or Railway scheduler:
    python manage.py process_recurring_tasks
"""

from django.core.management.base import BaseCommand

from apps.core.management.decorators import notify_on_error
from apps.life.services.recurrence import process_overdue_recurring_tasks


class Command(BaseCommand):
    help = 'Process completed recurring tasks and create next occurrences'

    @notify_on_error
    def handle(self, *args, **options):
        created_count = process_overdue_recurring_tasks()

        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Created {created_count} new recurring task(s)')
            )
        else:
            self.stdout.write('No new recurring tasks needed')
