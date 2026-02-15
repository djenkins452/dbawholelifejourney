"""
IOCD — Management command for generating observability snapshots.

Generates daily intelligence metrics snapshots. Supports backfilling
historical days with --days N.

Usage:
    python manage.py generate_observability_snapshots          # Yesterday only
    python manage.py generate_observability_snapshots --days 7 # Last 7 days

Project: Whole Life Journey
Path: apps/core/ai_observability/management/commands/generate_observability_snapshots.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.ai_observability.observability_engine import (
    generate_daily_snapshot,
)


class Command(BaseCommand):
    help = "Generate intelligence observability metrics snapshots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=1,
            help=(
                "Number of days to generate snapshots for (default: 1). "
                "Use --days 7 on first run to backfill."
            ),
        )

    def handle(self, *args, **options):
        days = options["days"]
        today = timezone.now().date()
        generated = 0
        skipped = 0
        errors = 0

        self.stdout.write(
            f"IOCD: Generating snapshots for last {days} day(s)..."
        )

        for i in range(days, 0, -1):
            target_date = today - timedelta(days=i)
            result = generate_daily_snapshot(target_date)

            if result is None:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"  ERROR: Failed to generate snapshot for {target_date}"
                    )
                )
            elif result.created_at and (
                timezone.now() - result.created_at
            ).total_seconds() < 5:
                # Newly created (within last 5 seconds)
                generated += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created snapshot for {target_date}"
                    )
                )
            else:
                skipped += 1
                self.stdout.write(
                    f"  Skipped {target_date} (already exists)"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nIOCD: Done — generated={generated}, "
                f"skipped={skipped}, errors={errors}"
            )
        )
