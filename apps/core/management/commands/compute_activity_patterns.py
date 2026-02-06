"""
Compute User Activity Patterns

Analyzes UserDailyActivity records to compute each user's typical
day start/end times. Stores results in UserActivityPattern for use
by the AI insight system.

Should be run daily (e.g., via scheduled job or cron).

Usage:
    python manage.py compute_activity_patterns
    python manage.py compute_activity_patterns --lookback-days=60
    python manage.py compute_activity_patterns --user-id=42
    python manage.py compute_activity_patterns --cleanup
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.core.models import UserActivityPattern, UserDailyActivity

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Compute user activity patterns from daily interaction data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--lookback-days',
            type=int,
            default=30,
            help='Number of days of activity data to analyze (default: 30)',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            default=None,
            help='Compute pattern for a specific user only',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Also clean up old UserDailyActivity records (90+ days)',
        )

    def handle(self, *args, **options):
        lookback_days = options['lookback_days']
        user_id = options['user_id']
        cleanup = options['cleanup']

        if user_id:
            users = User.objects.filter(id=user_id, is_active=True)
        else:
            # Only compute for users who have activity data
            user_ids = (
                UserDailyActivity.objects
                .values_list('user_id', flat=True)
                .distinct()
            )
            users = User.objects.filter(id__in=user_ids, is_active=True)

        computed = 0
        skipped = 0

        for user in users:
            pattern = UserActivityPattern.compute_for_user(
                user, lookback_days=lookback_days
            )
            if pattern:
                computed += 1
                logger.debug(
                    "Computed pattern for %s: start=%.1f, end=%.1f (%d days)",
                    user.email, pattern.typical_start_hour,
                    pattern.typical_end_hour, pattern.sample_days,
                )
            else:
                skipped += 1

        self.stdout.write(
            f"Activity patterns: {computed} computed, {skipped} skipped "
            f"(no data), lookback={lookback_days} days"
        )

        if cleanup:
            deleted = UserDailyActivity.cleanup_old_records()
            self.stdout.write(f"Cleaned up {deleted} old activity records")

        self.stdout.write(self.style.SUCCESS('Done.'))
