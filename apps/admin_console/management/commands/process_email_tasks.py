# ==============================================================================
# File: apps/admin_console/management/commands/process_email_tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to process emails and create tasks
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-16
# ==============================================================================
"""
Process Email Tasks Management Command

Polls the IMAP mailbox for emails in the "INBOX/Automate" folder and creates AdminTasks.

Usage:
    # Normal run (processes emails, creates tasks, moves to New Requests)
    python manage.py process_email_tasks

    # Dry run (shows what would be processed without making changes)
    python manage.py process_email_tasks --dry-run

    # Verbose output
    python manage.py process_email_tasks -v 2

Scheduling (Railway cron):
    Run at 6am, 12pm, 10pm via Railway scheduled tasks:
    python manage.py process_email_tasks

Environment Variables Required:
    EMAIL_INTAKE_HOST=mail.privateemail.com
    EMAIL_INTAKE_PORT=993
    EMAIL_INTAKE_USER=admin@wholelifejourney.com
    EMAIL_INTAKE_PASSWORD=<password>
"""

import logging

from django.core.management.base import BaseCommand

from apps.admin_console.email_intake import (
    EmailIntakeError,
    process_email_intake,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process emails from the INBOX/Automate folder and create AdminTasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbosity = options['verbosity']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        self.stdout.write('Processing email intake...')

        try:
            results = process_email_intake(dry_run=dry_run)

            # Report results
            if results['processed'] == 0 and results['errors'] == 0:
                self.stdout.write(self.style.SUCCESS('No emails to process'))
                return

            if results['processed'] > 0:
                self.stdout.write(
                    self.style.SUCCESS(f"Processed {results['processed']} email(s)")
                )

                if verbosity >= 2:
                    for task_info in results['tasks_created']:
                        self.stdout.write(
                            f"  - Task #{task_info['id']}: {task_info['title']}"
                        )

            if results['errors'] > 0:
                self.stdout.write(
                    self.style.ERROR(f"Errors: {results['errors']}")
                )
                for error_msg in results['error_messages']:
                    self.stdout.write(self.style.ERROR(f"  - {error_msg}"))

        except EmailIntakeError as e:
            self.stdout.write(self.style.ERROR(f"Email intake error: {e}"))
            logger.error(f"Email intake command failed: {e}")
            raise

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Unexpected error: {e}"))
            logger.exception("Email intake command failed unexpectedly")
            raise
