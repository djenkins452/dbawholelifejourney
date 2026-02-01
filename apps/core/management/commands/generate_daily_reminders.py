# ==============================================================================
# File: apps/core/management/commands/generate_daily_reminders.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to generate daily reminder notifications
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-20
# ==============================================================================
"""
Generate Daily Reminders - Create in-app notifications for scheduled reminders.

This command creates notifications for:
- Prayer reminders (for prayers with remind_daily=True)
- Reading plan reminders (at user's notification_reminder_time)

Usage:
    # Generate all reminders
    python manage.py generate_daily_reminders

    # Generate only prayer reminders
    python manage.py generate_daily_reminders --prayers-only

    # Generate only reading plan reminders
    python manage.py generate_daily_reminders --reading-plans-only

    # Dry run
    python manage.py generate_daily_reminders --dry-run

Schedule:
    - Prayer reminders: Run once daily in the morning (e.g., 6:00 AM)
    - Reading plan reminders: Run hourly to catch users at their preferred time

    "0 6 * * *" for morning prayer reminders
    "0 * * * *" for hourly reading plan check
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate daily reminder notifications for prayers and reading plans'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )
        parser.add_argument(
            '--prayers-only',
            action='store_true',
            help='Only generate prayer reminders',
        )
        parser.add_argument(
            '--reading-plans-only',
            action='store_true',
            help='Only generate reading plan reminders',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        prayers_only = options['prayers_only']
        reading_plans_only = options['reading_plans_only']
        verbosity = options['verbosity']

        from apps.core.services.notification_service import notification_service

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No notifications will be created'))

        total_created = 0

        # Generate prayer reminders
        if not reading_plans_only:
            if verbosity >= 1:
                self.stdout.write('Generating prayer reminders...')

            if dry_run:
                # Count potential reminders
                from django.contrib.auth import get_user_model
                User = get_user_model()

                users_with_prayers = User.objects.filter(
                    preferences__faith_enabled=True,
                    preferences__notifications_enabled=True,
                    prayerrequests__remind_daily=True,
                    prayerrequests__status='active',
                    prayerrequests__is_answered=False,
                ).distinct().count()

                self.stdout.write(f'  Would create reminders for {users_with_prayers} user(s)')
            else:
                count = notification_service.create_prayer_reminders()
                total_created += count
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(f'  Created {count} prayer reminder(s)'))

        # Generate reading plan reminders
        if not prayers_only:
            if verbosity >= 1:
                self.stdout.write('Generating reading plan reminders...')

            if dry_run:
                # Count potential reminders
                from django.contrib.auth import get_user_model
                User = get_user_model()

                now = timezone.now()
                current_hour = now.hour

                users = User.objects.filter(
                    preferences__faith_enabled=True,
                    preferences__notifications_enabled=True,
                    preferences__notification_reminder_time__hour=current_hour,
                ).count()

                self.stdout.write(f'  Would check {users} user(s) at hour {current_hour}')
            else:
                count = notification_service.create_reading_plan_reminders()
                total_created += count
                if verbosity >= 1:
                    self.stdout.write(self.style.SUCCESS(f'  Created {count} reading plan reminder(s)'))

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write('DRY RUN complete - no changes made')
        else:
            self.stdout.write(self.style.SUCCESS(f'Total notifications created: {total_created}'))
