# ==============================================================================
# File: send_pending_sms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to send pending SMS notifications
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
Send Pending SMS Management Command

Sends all pending SMS notifications that are due to be sent.
Should be run every 5 minutes via cron or external scheduler.

Usage:
    python manage.py send_pending_sms
    python manage.py send_pending_sms --dry-run
"""

from django.core.management.base import BaseCommand

from apps.sms.services import SMSNotificationService


class Command(BaseCommand):
    help = 'Send all pending SMS notifications that are due'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write("DRY RUN - No SMS will be sent")
            # Show pending notifications
            from django.utils import timezone
            from apps.sms.models import SMSNotification

            pending = SMSNotification.objects.filter(
                status=SMSNotification.STATUS_PENDING,
                scheduled_for__lte=timezone.now()
            ).select_related('user')

            if not pending:
                self.stdout.write(self.style.WARNING("No pending notifications to send"))
                return

            for notification in pending:
                self.stdout.write(
                    f"  [{notification.category}] {notification.user.email}: "
                    f"{notification.message[:50]}..."
                )

            self.stdout.write(self.style.SUCCESS(f"Would send {pending.count()} SMS"))
            return

        # Actually send notifications
        service = SMSNotificationService()
        results = service.send_pending_notifications()

        # Output results
        self.stdout.write(
            f"Sent: {results['sent']}, "
            f"Failed: {results['failed']}, "
            f"Skipped: {results['skipped']}"
        )

        if results['sent'] > 0:
            self.stdout.write(self.style.SUCCESS(f"Successfully sent {results['sent']} SMS"))
        elif results['failed'] > 0:
            self.stdout.write(self.style.ERROR(f"Failed to send {results['failed']} SMS"))
        else:
            self.stdout.write(self.style.WARNING("No pending notifications to send"))
