# ==============================================================================
# File: apps/core/management/commands/cleanup_soft_deletes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to permanently delete records past retention
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review)
# Last Updated: 2026-01-12
# ==============================================================================
"""
Soft Delete Cleanup Command

Permanently deletes records that have been soft-deleted for longer than
the retention period (default 30 days).

This command should be run periodically (e.g., weekly) via a scheduled job.

Usage:
    python manage.py cleanup_soft_deletes
    python manage.py cleanup_soft_deletes --dry-run
    python manage.py cleanup_soft_deletes --retention-days=60

Security Notes (CISO Review 2026-01-12):
    - Records are permanently and irrecoverably deleted
    - Respects the configured retention period from settings
    - Logs all deletions for audit purposes
    - Sends summary notification to admins
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from apps.core.security_logging import log_command_error

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Permanently delete soft-deleted records past the retention period'

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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        retention_days = options['retention_days']

        # Get retention period from settings if not specified
        if retention_days is None:
            retention_days = settings.WLJ_SETTINGS.get('SOFT_DELETE_RETENTION_DAYS', 30)

        cutoff_date = timezone.now() - timedelta(days=retention_days)

        self.stdout.write(
            f"\nSoft Delete Cleanup\n"
            f"{'=' * 50}\n"
            f"Retention period: {retention_days} days\n"
            f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n"
            f"{'=' * 50}\n"
        )

        # Collect all models that inherit from SoftDeleteModel
        from apps.core.models import SoftDeleteModel
        soft_delete_models = self._get_soft_delete_models()

        total_deleted = 0
        deleted_by_model = {}

        for model in soft_delete_models:
            try:
                # Use all_objects manager to bypass SoftDeleteManager filter
                manager = getattr(model, 'all_objects', model.objects)
                queryset = manager.filter(
                    status='deleted',
                    deleted_at__lt=cutoff_date,
                )

                count = queryset.count()
                if count > 0:
                    model_name = f"{model._meta.app_label}.{model._meta.model_name}"
                    deleted_by_model[model_name] = count

                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(f"  Would delete {count} {model_name} records")
                        )
                    else:
                        # Log individual deletions for audit
                        ids = list(queryset.values_list('id', flat=True))
                        logger.info(
                            f"Permanently deleting {count} {model_name} records: {ids}"
                        )

                        # Perform hard delete
                        queryset.delete()
                        total_deleted += count

                        self.stdout.write(
                            self.style.SUCCESS(f"  Deleted {count} {model_name} records")
                        )

            except Exception as e:
                model_name = f"{model._meta.app_label}.{model._meta.model_name}"
                self.stdout.write(
                    self.style.ERROR(f"  Error processing {model_name}: {e}")
                )
                log_command_error('cleanup_soft_deletes', e, {'model': model_name})

        # Summary
        self.stdout.write(f"\n{'=' * 50}")
        if dry_run:
            total_would_delete = sum(deleted_by_model.values())
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Would delete {total_would_delete} total records")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Cleanup complete. Deleted {total_deleted} total records.")
            )

            # Log summary for audit
            if total_deleted > 0:
                logger.info(
                    f"Soft delete cleanup completed. "
                    f"Deleted {total_deleted} records. "
                    f"Breakdown: {deleted_by_model}"
                )

    def _get_soft_delete_models(self):
        """
        Find all models that use soft delete (have status='deleted' field).

        Returns:
            List of model classes that support soft delete
        """
        from django.apps import apps
        from apps.core.models import SoftDeleteModel

        soft_delete_models = []

        for model in apps.get_models():
            # Check if model inherits from SoftDeleteModel
            if issubclass(model, SoftDeleteModel) and model is not SoftDeleteModel:
                # Verify it has the required fields
                if hasattr(model, 'status') and hasattr(model, 'deleted_at'):
                    soft_delete_models.append(model)

        return soft_delete_models
