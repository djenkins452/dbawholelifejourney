# ==============================================================================
# File: apps/core/management/commands/cleanup_api_logs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to clean up old API request logs
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review)
# Last Updated: 2026-01-12
# ==============================================================================
"""
API Request Log Cleanup Command

Deletes API request logs older than the retention period (default 30 days).
Anomaly records can optionally be retained longer for security analysis.

This command should be run periodically (e.g., daily) via a scheduled job.

Usage:
    python manage.py cleanup_api_logs
    python manage.py cleanup_api_logs --dry-run
    python manage.py cleanup_api_logs --retention-days=60
    python manage.py cleanup_api_logs --keep-anomalies

Security Notes (CISO Review 2026-01-12):
    - Part of API request logging infrastructure
    - Logs are permanently deleted after retention period
    - Anomaly logs can be retained longer for security review
    - Logs deletion summary for audit purposes
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.security_logging import log_command_error

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete API request logs older than the retention period'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=None,
            help='Override retention period (days). Default from settings.',
        )
        parser.add_argument(
            '--keep-anomalies',
            action='store_true',
            help='Retain anomaly records for twice the normal retention period',
        )

    def handle(self, *args, **options):
        from apps.core.models import APIRequestLog

        dry_run = options['dry_run']
        keep_anomalies = options['keep_anomalies']
        retention_days = options['retention_days']

        # Get retention period from settings if not specified
        if retention_days is None:
            retention_days = settings.WLJ_SETTINGS.get('API_LOG_RETENTION_DAYS', 30)

        cutoff_date = timezone.now() - timedelta(days=retention_days)

        self.stdout.write(
            f"\nAPI Request Log Cleanup\n"
            f"{'=' * 50}\n"
            f"Retention period: {retention_days} days\n"
            f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Keep anomalies: {keep_anomalies}\n"
            f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n"
            f"{'=' * 50}\n"
        )

        try:
            # Build queryset for old logs
            queryset = APIRequestLog.objects.filter(created_at__lt=cutoff_date)

            if keep_anomalies:
                # Exclude anomalies - they get double retention
                anomaly_cutoff = timezone.now() - timedelta(days=retention_days * 2)
                normal_logs = queryset.filter(is_anomaly=False)
                old_anomalies = APIRequestLog.objects.filter(
                    is_anomaly=True,
                    created_at__lt=anomaly_cutoff
                )

                normal_count = normal_logs.count()
                anomaly_count = old_anomalies.count()
                total_count = normal_count + anomaly_count

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Would delete {normal_count} normal logs "
                            f"(older than {retention_days} days)"
                        )
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Would delete {anomaly_count} anomaly logs "
                            f"(older than {retention_days * 2} days)"
                        )
                    )
                else:
                    # Delete normal logs
                    if normal_count > 0:
                        normal_logs.delete()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  Deleted {normal_count} normal logs"
                            )
                        )

                    # Delete old anomalies
                    if anomaly_count > 0:
                        old_anomalies.delete()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  Deleted {anomaly_count} old anomaly logs"
                            )
                        )
            else:
                # Delete all old logs regardless of anomaly status
                total_count = queryset.count()

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Would delete {total_count} logs "
                            f"(older than {retention_days} days)"
                        )
                    )
                else:
                    if total_count > 0:
                        queryset.delete()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  Deleted {total_count} logs"
                            )
                        )

            # Summary
            self.stdout.write(f"\n{'=' * 50}")

            # Get current stats
            remaining_count = APIRequestLog.objects.count()
            anomaly_remaining = APIRequestLog.objects.filter(is_anomaly=True).count()

            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN complete. No records deleted.")
                )
            else:
                logger.info(
                    f"API log cleanup completed. "
                    f"Deleted {total_count if not keep_anomalies else normal_count + anomaly_count} records. "
                    f"Remaining: {remaining_count} ({anomaly_remaining} anomalies)"
                )
                self.stdout.write(
                    self.style.SUCCESS("Cleanup complete.")
                )

            self.stdout.write(
                f"Remaining logs: {remaining_count} ({anomaly_remaining} anomalies)\n"
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error during cleanup: {e}")
            )
            log_command_error('cleanup_api_logs', e)
            raise
