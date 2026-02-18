"""
Whole Life Journey — Sync CoS Documentation Command

Project: Whole Life Journey
Path: apps/core/management/commands/sync_cos_docs.py
Purpose: Management command to sync CoS admin guide from code

Usage:
    python manage.py sync_cos_docs           # Sync only if checksum changed
    python manage.py sync_cos_docs --force   # Force sync regardless
    python manage.py sync_cos_docs --validate  # Validate only, don't sync

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sync Chief of Staff documentation to admin guide from live code"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if checksum unchanged',
        )
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Validate registry only — do not sync',
        )

    def handle(self, *args, **options):
        if options['validate']:
            self._handle_validate()
            return

        from apps.core.ai_docs.cos_doc_sync import sync_cos_admin_guide

        force = options['force']
        result = sync_cos_admin_guide(force=force)

        if result['synced']:
            self.stdout.write(self.style.SUCCESS(
                f"CoS docs synced: "
                f"{result['articles_created']} created, "
                f"{result['articles_updated']} updated, "
                f"{result['articles_removed']} removed"
            ))
            self.stdout.write(f"  Checksum: {result['checksum']}")

            validation = result['validation']
            if not validation['is_valid']:
                self.stdout.write(self.style.WARNING(
                    f"  Validation warnings ({len(validation['errors'])}):"
                ))
                for err in validation['errors']:
                    self.stdout.write(f"    - {err}")
        else:
            self.stdout.write(self.style.NOTICE(
                f"Skipped: {result['reason']}"
            ))

    def _handle_validate(self):
        from apps.core.ai_docs.cos_doc_registry import validate_registry

        is_valid, errors = validate_registry()

        if is_valid:
            self.stdout.write(self.style.SUCCESS(
                "Registry validation passed — all engines, functions, "
                "and model fields verified."
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"Registry validation failed ({len(errors)} errors):"
            ))
            for err in errors:
                self.stdout.write(f"  - {err}")
