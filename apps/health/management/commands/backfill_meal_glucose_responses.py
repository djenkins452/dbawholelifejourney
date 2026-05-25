"""
Backfill MealGlucoseResponse rows for historical FoodEntries.

Iterates each user's FoodEntries in a date range, runs the deterministic
classifier, and reports a per-status tally. Idempotent — re-running the
same range does no work on already-classified FoodEntries unless --force.

Usage:
    python manage.py backfill_meal_glucose_responses \\
        --user dannyjenkins71@gmail.com \\
        --start 2026-04-01 --end 2026-05-25

Flags:
    --user <email>   Limit to one user. Default: all users with any
                     FoodEntry in the date range.
    --start <ISO>    Inclusive start date. Default: 30 days ago.
    --end <ISO>      Inclusive end date. Default: today.
    --force          Reclassify already-classified entries.
    --dry-run        Run the classifier without persisting; report tally only.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.health.services.meal_response_classifier import (
    ClassifierResult,
    classify_meal_glucose_response,
)


User = get_user_model()


class Command(BaseCommand):
    help = "Backfill MealGlucoseResponse rows for historical FoodEntries."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=str, default=None)
        parser.add_argument("--start", type=str, default=None)
        parser.add_argument("--end", type=str, default=None)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--dry-run", action="store_true", default=False)

    def handle(self, *args, **options):
        from apps.health.models import FoodEntry

        end_date = (
            date.fromisoformat(options["end"]) if options["end"]
            else date.today()
        )
        start_date = (
            date.fromisoformat(options["start"]) if options["start"]
            else end_date - timedelta(days=30)
        )
        force = options["force"]
        dry_run = options["dry_run"]

        qs = FoodEntry.objects.filter(
            logged_date__gte=start_date,
            logged_date__lte=end_date,
        ).order_by("user_id", "logged_date", "logged_time")

        if options["user"]:
            try:
                user_obj = User.objects.get(email=options["user"])
            except User.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"No user with email {options['user']!r}")
                )
                return
            qs = qs.filter(user=user_obj)

        total = qs.count()
        self.stdout.write(
            f"Backfilling MealGlucoseResponse over {start_date}..{end_date}: "
            f"{total} FoodEntry candidates"
        )

        tally: Counter = Counter()
        # Wrap in atomic+rollback for --dry-run so persisted side effects
        # are reverted at the end while still letting the classifier
        # exercise its writes during the run.
        if dry_run:
            with transaction.atomic():
                for entry in qs.iterator():
                    _, status = classify_meal_glucose_response(entry, force=force)
                    tally[status] += 1
                transaction.set_rollback(True)
        else:
            for entry in qs.iterator():
                _, status = classify_meal_glucose_response(entry, force=force)
                tally[status] += 1

        self.stdout.write("Result tally:")
        for status_label in (
            ClassifierResult.OK,
            ClassifierResult.SKIPPED_NO_TIME,
            ClassifierResult.SKIPPED_NO_BASELINE,
            ClassifierResult.SKIPPED_INSUFFICIENT_POST_MEAL,
            ClassifierResult.SKIPPED_PRIOR_MEAL,
            ClassifierResult.SKIPPED_WORKOUT_IN_WINDOW,
            ClassifierResult.SKIPPED_ALREADY_CLASSIFIED,
        ):
            self.stdout.write(f"  {status_label}: {tally.get(status_label, 0)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no rows persisted."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done: {tally.get(ClassifierResult.OK, 0)} new classifications."
                )
            )
