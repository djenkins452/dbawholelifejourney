"""
DBE — Generate Daily Briefings management command.

Loops all active users with ai_enabled=True and generates a daily briefing
for each. Intended to be scheduled via Railway cron or similar.

Usage:
    python manage.py generate_daily_briefings
    python manage.py generate_daily_briefings --user user@example.com
"""

import logging
import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.core.ai_briefing.briefing_engine import generate_daily_briefing

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Generate daily briefings for all active users with AI enabled."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            help="Generate briefing for a specific user email only.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count eligible users without generating briefings.",
        )

    def handle(self, *args, **options):
        start = time.time()
        email = options.get("user")
        dry_run = options.get("dry_run", False)

        if email:
            users = User.objects.filter(email=email, is_active=True)
            if not users.exists():
                self.stderr.write(self.style.ERROR(f"User not found: {email}"))
                return
        else:
            users = User.objects.filter(
                is_active=True,
                preferences__ai_enabled=True,
            )

        total = users.count()

        if dry_run:
            self.stdout.write(f"Dry run: {total} eligible users")
            return

        self.stdout.write(f"Generating briefings for {total} users...")

        generated = 0
        skipped = 0
        errors = 0

        for user in users.iterator():
            try:
                briefing = generate_daily_briefing(user)
                if briefing:
                    generated += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                logger.error(
                    f"DBE: Failed to generate briefing for user {user.id}: {e}",
                    exc_info=True,
                )

        elapsed = time.time() - start
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {generated} generated, {skipped} skipped, "
                f"{errors} errors in {elapsed:.1f}s"
            )
        )
