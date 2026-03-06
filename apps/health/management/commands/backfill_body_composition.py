"""
Backfill BodyCompositionEntry from historical WeightEntry data.

Handles two types of backfill:
1. Direct migration: body_fat_percentage and lean_body_mass fields on WeightEntry
   are copied to BodyCompositionEntry rows.
2. Derived metrics: When a WeightEntry has weight > 0 AND body_fat_percentage,
   lean_mass and fat_mass are calculated and stored.

Usage:
    python manage.py backfill_body_composition           # Backfill all users
    python manage.py backfill_body_composition --dry-run  # Preview without writing
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill BodyCompositionEntry from WeightEntry (direct + derived metrics)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be created without writing to the database",
        )

    def handle(self, *args, **options):
        from apps.health.models import BodyCompositionEntry, WeightEntry
        from apps.health.services.body_composition_service import calculate_body_composition

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
        created_derived_lm = 0
        created_derived_fm = 0
        skipped_bf = 0
        skipped_lm = 0
        skipped_derived_lm = 0
        skipped_derived_fm = 0

        for entry in weight_entries.iterator():
            measurement_date = entry.recorded_at.date()
            source = entry.source or "apple_health"

            # --- Direct migration: body fat percentage ---
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
                    created_bf += 1

            # --- Direct migration: lean body mass from HealthKit ---
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
                    created_lm += 1

            # --- Derived metrics: lean_mass and fat_mass from weight + body_fat ---
            if entry.value and entry.value > 0 and entry.body_fat_percentage is not None:
                result = calculate_body_composition(entry.value, entry.body_fat_percentage)
                if result is None:
                    continue

                # Derived lean_mass (only if not already created from direct HealthKit value above)
                lm_exists = BodyCompositionEntry.objects.filter(
                    user=entry.user,
                    metric_name="lean_mass",
                    measurement_date=measurement_date,
                ).exists()
                if lm_exists:
                    skipped_derived_lm += 1
                elif not dry_run:
                    BodyCompositionEntry.objects.create(
                        user=entry.user,
                        metric_name="lean_mass",
                        value=result["lean_mass"],
                        unit="lb",
                        measurement_date=measurement_date,
                        source=source,
                    )
                    created_derived_lm += 1
                else:
                    created_derived_lm += 1

                # Derived fat_mass
                fm_exists = BodyCompositionEntry.objects.filter(
                    user=entry.user,
                    metric_name="fat_mass",
                    measurement_date=measurement_date,
                ).exists()
                if fm_exists:
                    skipped_derived_fm += 1
                elif not dry_run:
                    BodyCompositionEntry.objects.create(
                        user=entry.user,
                        metric_name="fat_mass",
                        value=result["fat_mass"],
                        unit="lb",
                        measurement_date=measurement_date,
                        source=source,
                    )
                    created_derived_fm += 1
                else:
                    created_derived_fm += 1

        prefix = "[DRY RUN] Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}:\n"
            f"  Direct: {created_bf} body_fat_pct + {created_lm} lean_mass "
            f"(skipped {skipped_bf} + {skipped_lm})\n"
            f"  Derived: {created_derived_lm} lean_mass + {created_derived_fm} fat_mass "
            f"(skipped {skipped_derived_lm} + {skipped_derived_fm})"
        ))
