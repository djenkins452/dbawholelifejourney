# ==============================================================================
# File: import_clarity_csv.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Import Dexcom Clarity CSV export into GlucoseEntry records
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# Last Updated: 2026-01-04
# ==============================================================================
"""
Management command to import Dexcom Clarity CSV export files.

Imports blood glucose (EGV) readings from Clarity export CSV files into
GlucoseEntry records. Skips duplicate entries based on timestamp.

Usage:
    python manage.py import_clarity_csv <csv_file> <user_email>
    python manage.py import_clarity_csv clarity_export.csv dannyjenkins71@gmail.com
    python manage.py import_clarity_csv --dry-run clarity_export.csv user@example.com
"""

import csv
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.health.models import GlucoseEntry
from apps.users.models import User


class Command(BaseCommand):
    help = 'Import Dexcom Clarity CSV export into GlucoseEntry records'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the Clarity CSV export file'
        )
        parser.add_argument(
            'user_email',
            type=str,
            help='Email of the user to import data for'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse and validate without saving to database'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        user_email = options['user_email']
        dry_run = options['dry_run']

        # Find the user
        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            raise CommandError(f"User with email '{user_email}' not found")

        self.stdout.write(f"Importing Clarity data for user: {user.email}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no data will be saved"))

        # Parse the CSV file
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f"CSV file not found: {csv_file}")
        except Exception as e:
            raise CommandError(f"Error reading CSV file: {e}")

        self.stdout.write(f"Found {len(rows)} rows in CSV")

        # Filter to EGV (Estimated Glucose Value) rows only
        egv_rows = [
            row for row in rows
            if row.get('Event Type') == 'EGV' and row.get('Glucose Value (mg/dL)')
        ]
        self.stdout.write(f"Found {len(egv_rows)} EGV (glucose) readings")

        # Get existing timestamps to avoid duplicates
        existing_timestamps = set(
            GlucoseEntry.objects.filter(
                user=user,
                source='imported'
            ).values_list('recorded_at', flat=True)
        )
        self.stdout.write(f"Found {len(existing_timestamps)} existing imported entries")

        # Parse and prepare entries
        entries_to_create = []
        skipped_duplicates = 0
        skipped_invalid = 0

        for row in egv_rows:
            try:
                # Parse timestamp (format: YYYY-MM-DDThh:mm:ss)
                timestamp_str = row.get('Timestamp (YYYY-MM-DDThh:mm:ss)', '')
                if not timestamp_str:
                    skipped_invalid += 1
                    continue

                # Parse the timestamp and make it timezone-aware
                dt = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
                recorded_at = timezone.make_aware(dt, timezone.get_current_timezone())

                # Check for duplicate
                if recorded_at in existing_timestamps:
                    skipped_duplicates += 1
                    continue

                # Parse glucose value
                glucose_str = row.get('Glucose Value (mg/dL)', '')
                if not glucose_str:
                    skipped_invalid += 1
                    continue

                glucose_value = Decimal(glucose_str)

                # Create entry object (don't save yet)
                entry = GlucoseEntry(
                    user=user,
                    value=glucose_value,
                    unit='mg/dL',
                    context='cgm',
                    recorded_at=recorded_at,
                    source='imported',
                    notes='Imported from Dexcom Clarity CSV'
                )
                entries_to_create.append(entry)
                existing_timestamps.add(recorded_at)  # Track to avoid duplicates within file

            except (ValueError, KeyError) as e:
                skipped_invalid += 1
                continue

        self.stdout.write(f"Entries to create: {len(entries_to_create)}")
        self.stdout.write(f"Skipped (duplicates): {skipped_duplicates}")
        self.stdout.write(f"Skipped (invalid): {skipped_invalid}")

        if not dry_run and entries_to_create:
            # Bulk create entries
            with transaction.atomic():
                GlucoseEntry.objects.bulk_create(entries_to_create, batch_size=1000)
            # Invalidate cache since bulk_create bypasses Django signals
            from assistant.data_service import invalidate_user_data_cache
            invalidate_user_data_cache(user.id, 'glucose')
            self.stdout.write(
                self.style.SUCCESS(f"Successfully imported {len(entries_to_create)} glucose entries")
            )
        elif dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"DRY RUN complete - would import {len(entries_to_create)} entries")
            )
        else:
            self.stdout.write(self.style.WARNING("No new entries to import"))

        # Summary stats
        if entries_to_create:
            min_date = min(e.recorded_at for e in entries_to_create)
            max_date = max(e.recorded_at for e in entries_to_create)
            values = [e.value for e in entries_to_create]
            avg_value = sum(values) / len(values)

            self.stdout.write("\nImport Summary:")
            self.stdout.write(f"  Date range: {min_date.date()} to {max_date.date()}")
            self.stdout.write(f"  Average glucose: {avg_value:.1f} mg/dL")
            self.stdout.write(f"  Min glucose: {min(values)} mg/dL")
            self.stdout.write(f"  Max glucose: {max(values)} mg/dL")
