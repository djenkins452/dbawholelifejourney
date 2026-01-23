# ==============================================================================
# File: apps/core/management/commands/send_notification_digest.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to send daily notification digest emails
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-20
# ==============================================================================
"""
Send Notification Digest - Daily email digest of pending notifications.

This command should be scheduled to run daily at 4:45 AM to deliver
notification digests before users typically start their day.

Usage:
    # Send digest to all eligible users
    python manage.py send_notification_digest

    # Dry run (don't actually send)
    python manage.py send_notification_digest --dry-run

    # Verbose output
    python manage.py send_notification_digest -v 2

Schedule:
    Add to Railway cron or django-apscheduler:
    "45 4 * * *" (4:45 AM daily)
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.utils import user_log_id

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send daily notification digest emails to users with pending notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Send digest to a specific user by email address',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        specific_user = options.get('user')
        verbosity = options['verbosity']

        from apps.core.services.notification_service import notification_service

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No emails will be sent'))

        # Get users to send digest to
        if specific_user:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                users = [User.objects.get(email=specific_user)]
                self.stdout.write(f'Sending to specific user: {specific_user}')
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User not found: {specific_user}'))
                return
        else:
            users = list(notification_service.get_users_for_digest())

        if not users:
            self.stdout.write('No users have pending digest notifications.')
            return

        self.stdout.write(f'Found {len(users)} user(s) with pending notifications')

        # Send digests
        sent_count = 0
        error_count = 0

        for user in users:
            if verbosity >= 2:
                self.stdout.write(f'  Processing: {user.email}')

            if dry_run:
                # In dry run, just count
                from apps.core.models import Notification
                pending = Notification.get_pending_email_notifications(user).count()
                self.stdout.write(f'    Would send: {pending} notifications')
                sent_count += 1
            else:
                try:
                    success = notification_service.send_daily_digest(user)
                    if success:
                        sent_count += 1
                        if verbosity >= 2:
                            self.stdout.write(self.style.SUCCESS(f'    Sent digest'))
                    else:
                        error_count += 1
                        if verbosity >= 2:
                            self.stdout.write(self.style.WARNING(f'    No digest sent (empty or error)'))
                except Exception as e:
                    error_count += 1
                    logger.error(f'Failed to send digest to {user_log_id(user)}: {e}')
                    if verbosity >= 1:
                        self.stdout.write(self.style.ERROR(f'    Error: {e}'))

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'Would have sent {sent_count} digest(s)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Sent: {sent_count} digest(s)'))
            if error_count:
                self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
