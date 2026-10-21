# ==============================================================================
# File: apps/core/management/commands/cleanup_api_logs.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to clean up old API request logs
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review)
# Last Updated: 2026-10-21 (delegates to prune_telemetry; batched)
# ==============================================================================
"""
API Request Log Cleanup Command

Thin alias for ``prune_telemetry --only api_request_log``. The retention window
is WLJ_SETTINGS['API_LOG_RETENTION_DAYS'] (30); anomaly rows are always kept
90 days for security review (policy in apps/core/data_retention.py). Deletion
is batched — the previous single unbatched DELETE was never scheduled.

Usage:
    python manage.py cleanup_api_logs
    python manage.py cleanup_api_logs --dry-run
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Delete API request logs older than the retention period'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        call_command(
            'prune_telemetry',
            only=['api_request_log'],
            dry_run=options['dry_run'],
            stdout=self.stdout,
        )
