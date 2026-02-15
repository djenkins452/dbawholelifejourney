"""
Management command to run the PGE (Proactive Guidance Engine) for all users.

Usage:
    python manage.py run_guidance_engine              # All active users
    python manage.py run_guidance_engine --user=42    # Single user
    python manage.py run_guidance_engine --expire     # Only expire old items

Designed to be run daily via cron or scheduler.
"""

import logging

from django.core.management.base import BaseCommand

from apps.core.ai_guidance.guidance_engine import (
    expire_old_guidance,
    generate_guidance,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Proactive Guidance Engine for users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            help="Run for a specific user ID only",
        )
        parser.add_argument(
            "--expire",
            action="store_true",
            help="Only expire old guidance items (skip generation)",
        )

    def handle(self, *args, **options):
        from apps.users.models import User

        # Always expire old items first
        expired = expire_old_guidance()
        self.stdout.write(f"Expired {expired} old guidance items")

        if options["expire"]:
            return

        if options["user"]:
            try:
                user = User.objects.get(id=options["user"])
                items = generate_guidance(user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated {len(items)} guidance items for {user.email}"
                    )
                )
            except User.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"User {options['user']} not found")
                )
            return

        # Run for all active users
        users = User.objects.filter(is_active=True)
        total_generated = 0
        total_users = 0

        for user in users.iterator():
            try:
                items = generate_guidance(user)
                if items:
                    total_generated += len(items)
                    total_users += 1
            except Exception as e:
                logger.error(
                    f"PGE: Failed for user {user.id}: {e}",
                    exc_info=True,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"PGE complete: {total_generated} items for {total_users} users"
            )
        )
