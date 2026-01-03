# ==============================================================================
# File: purge_old_signups.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to purge SignupAttempt records older than
#              the retention period (default 90 days) for GDPR/privacy compliance
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

"""
Purge Old Signup Attempts Command

Enforces the 90-day retention policy on SignupAttempt records by deleting
records older than the specified threshold. This supports GDPR compliance
and prevents unbounded growth of the signup audit table.

Usage:
    python manage.py purge_old_signups           # Delete records > 90 days old
    python manage.py purge_old_signups --dry-run # Preview without deleting
    python manage.py purge_old_signups --days=30 # Custom retention period

The command is idempotent and safe to run repeatedly (e.g., via cron or
scheduled task).
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.models import SignupAttempt


class Command(BaseCommand):
    help = "Purge SignupAttempt records older than the retention period (default 90 days)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview deletions without actually deleting records",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Retention period in days (default: 90)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        retention_days = options["days"]
        verbosity = options["verbosity"]

        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=retention_days)

        # Find records to delete
        old_records = SignupAttempt.objects.filter(created_at__lt=cutoff_date)
        count = old_records.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No SignupAttempt records older than {retention_days} days."
                )
            )
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {count} SignupAttempt record(s) "
                    f"older than {retention_days} days (before {cutoff_date.date()})."
                )
            )
            if verbosity >= 2:
                # Show breakdown by status
                self.stdout.write("\nBreakdown by status:")
                for status, _ in SignupAttempt.STATUS_CHOICES:
                    status_count = old_records.filter(status=status).count()
                    if status_count > 0:
                        self.stdout.write(f"  - {status}: {status_count}")
        else:
            # Actually delete the records
            deleted_count, _ = old_records.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {deleted_count} SignupAttempt record(s) "
                    f"older than {retention_days} days."
                )
            )
