"""
One-time backfill: populate BodyCompositionEntry from historical WeightEntry data.

HealthKit ingestion historically stored body fat % and lean body mass on
WeightEntry fields. The pipeline now creates BodyCompositionEntry during
ingestion, but historical rows need migrating.

Usage:
    python manage.py backfill_body_composition           # Backfill all users
    python manage.py backfill_body_composition --dry-run  # Preview without writing
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill BodyCompositionEntry from WeightEntry body_fat_percentage and lean_body_mass"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be created without writing to the database",
        )

    def handle(self, *args, **options):
        from apps.health.models import BodyCompositionEntry, WeightEntry

        dry_run = options["dry_run"]
        verbosity = options["verbosity"]

        # Find all WeightEntry rows with body composition data
        weight_entries = WeightEntry.objects.filter(
            Q(body_fat_percentage__isnull=False) | Q(lean_body_mass__isnull=False)
        ).select_related("user").order_by("recorded_at")

        total = weight_entries.count()
        if verbosity >= 1:
            self.stdout.write(f"Found {total} WeightEntry rows with body composition data")

        created_bf = 0
        created_lm = 0
        skipped_bf = 0
        skipped_lm = 0

        for entry in weight_entries.iterator():
            measurement_date = entry.recorded_at.date()
            source = entry.source or "apple_health"

            # Body fat percentage
            if entry.body_fat_percentage is not None:
                exists = BodyCompositionEntry.objects.filter(
                    user=entry.user,
                    metric_name="body_fat_pct",
                    measurement_date=measurement_date,
                ).exists()

                if exists:
                    skipped_bf += 1
                elif not dry_run:
                    BodyCompositionEntry.objects.create(
                        user=entry.user,
                        metric_name="body_fat_pct",
                        value=entry.body_fat_percentage,
                        unit="pct",
                        measurement_date=measurement_date,
                        source=source,
                    )
                    created_bf += 1
                else:
                    created_bf += 1  # Count what would be created

            # Lean body mass
            if entry.lean_body_mass is not None:
                exists = BodyCompositionEntry.objects.filter(
                    user=entry.user,
                    metric_name="lean_mass",
                    measurement_date=measurement_date,
                ).exists()

                if exists:
                    skipped_lm += 1
                elif not dry_run:
                    BodyCompositionEntry.objects.create(
                        user=entry.user,
                        metric_name="lean_mass",
                        value=entry.lean_body_mass,
                        unit="lb",
                        measurement_date=measurement_date,
                        source=source,
                    )
                    created_lm += 1
                else:
                    created_lm += 1  # Count what would be created

        prefix = "[DRY RUN] Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}: {created_bf} body_fat_pct + {created_lm} lean_mass entries "
            f"(skipped {skipped_bf} body_fat + {skipped_lm} lean_mass duplicates)"
        ))
