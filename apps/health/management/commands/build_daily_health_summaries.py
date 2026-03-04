"""
Management command to build DailyHealthSummary rows.

Usage:
    # Build yesterday for all active users (nightly default)
    python manage.py build_daily_health_summaries

    # Build for a specific user
    python manage.py build_daily_health_summaries --user 42

    # Backfill a date range
    python manage.py build_daily_health_summaries --from 2026-01-01 --to 2026-02-28

    # Rebuild last N days for all active users
    python manage.py build_daily_health_summaries --days 7

    # Skip score computation (faster for bulk backfill)
    python manage.py build_daily_health_summaries --from 2025-06-01 --to 2026-02-28 --no-scores
"""

import logging
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Build DailyHealthSummary rows with health + recovery scores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            help="User ID to process (default: all active users)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=1,
            help="Number of days to process going back from today (default: 1 = yesterday)",
        )
        parser.add_argument(
            "--from",
            dest="from_date",
            type=str,
            help="Start date (YYYY-MM-DD) for backfill",
        )
        parser.add_argument(
            "--to",
            dest="to_date",
            type=str,
            help="End date (YYYY-MM-DD) for backfill",
        )
        parser.add_argument(
            "--no-scores",
            action="store_true",
            help="Skip health/recovery score computation (just build summaries)",
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        from apps.health.services.score_pipeline import ScorePipeline

        User = get_user_model()

        # Determine users
        if options["user"]:
            users = User.objects.filter(id=options["user"], is_active=True)
            if not users.exists():
                raise CommandError(f"No active user found with ID {options['user']}")
        else:
            users = User.objects.filter(is_active=True)

        # Determine date range
        if options["from_date"]:
            start = datetime.strptime(options["from_date"], "%Y-%m-%d").date()
            end = (
                datetime.strptime(options["to_date"], "%Y-%m-%d").date()
                if options["to_date"]
                else date.today() - timedelta(days=1)
            )
        else:
            days = options["days"]
            end = date.today() - timedelta(days=1)
            start = end - timedelta(days=days - 1)

        compute_scores = not options["no_scores"]
        builder = DailyHealthSummaryBuilder()

        user_count = users.count()
        self.stdout.write(
            f"Building summaries for {user_count} user(s) "
            f"from {start} to {end} "
            f"({'with' if compute_scores else 'without'} scores)"
        )

        total_built = 0
        for user in users.iterator():
            current = start
            user_count_built = 0
            while current <= end:
                try:
                    builder.build_for_date(user, current)
                    if compute_scores:
                        ScorePipeline.compute_scores(user, current)
                    user_count_built += 1
                except Exception:
                    logger.error(
                        "Failed for user %s on %s", user.email, current,
                        exc_info=True,
                    )
                current += timedelta(days=1)

            total_built += user_count_built
            self.stdout.write(f"  {user.email}: {user_count_built} days processed")

        self.stdout.write(self.style.SUCCESS(
            f"Done. {total_built} total summaries built."
        ))
