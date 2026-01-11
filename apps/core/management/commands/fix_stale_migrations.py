# ==============================================================================
# File: apps/core/management/commands/fix_stale_migrations.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fix stale migration records before Django migrate runs
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-11
# ==============================================================================
"""
Fix stale/broken migration records in django_migrations table.

This command MUST run BEFORE 'manage.py migrate' because the error occurs
when Django builds the migration dependency graph, which happens before
any migration operations.

The command directly connects to the database and removes any stale records
that reference non-existent parent migrations.

Usage (in Procfile):
    python manage.py fix_stale_migrations && python manage.py migrate
"""
from django.core.management.base import BaseCommand
from django.db import connection


# List of known stale migrations to remove
# Format: (app_label, migration_name)
STALE_MIGRATIONS = [
    # 2026-01-11: core.0012_feature_request_detection_release_note depends on
    # core.0011_add_sms_models which never existed. The correct migration is
    # core.0038_feature_request_detection_release_note which depends on 0037.
    ('core', '0012_feature_request_detection_release_note'),
    ('core', '0011_add_sms_models'),
]


class Command(BaseCommand):
    help = 'Fix stale migration records before Django migrate runs'

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)

        # Only needed for production PostgreSQL
        if connection.vendor != 'postgresql':
            if verbosity >= 1:
                self.stdout.write('Skipping: not PostgreSQL')
            return

        fixed_count = 0
        with connection.cursor() as cursor:
            for app, name in STALE_MIGRATIONS:
                cursor.execute(
                    "SELECT id FROM django_migrations WHERE app = %s AND name = %s",
                    [app, name]
                )
                row = cursor.fetchone()
                if row:
                    if verbosity >= 1:
                        self.stdout.write(f'Removing stale migration: {app}.{name}')
                    cursor.execute(
                        "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                        [app, name]
                    )
                    fixed_count += 1

        if fixed_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Fixed {fixed_count} stale migration(s)'))
        elif verbosity >= 1:
            self.stdout.write('No stale migrations found')
