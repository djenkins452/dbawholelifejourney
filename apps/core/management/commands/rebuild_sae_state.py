"""
One-time management command to rebuild SAE state for all active users.

Use after deploying state_builder changes that add new fields —
the persisted UserState.state_data won't contain those fields until
the ISE cycle runs rebuild_user_state(). This forces an immediate rebuild.

Usage:
    python manage.py rebuild_sae_state
    python manage.py rebuild_sae_state --user=dannyjenkins71@gmail.com
"""

import logging
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Rebuild SAE state for all active users (or a single user)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Rebuild for a single user by email (default: all active users).",
        )

    def handle(self, *args, **options):
        from apps.core.ai_state.state_engine import rebuild_user_state
        from apps.users.models import User

        email = options.get("user")
        if email:
            users = User.objects.filter(email=email, is_active=True)
        else:
            users = User.objects.filter(is_active=True)

        total = users.count()
        self.stdout.write(f"Rebuilding SAE state for {total} user(s)...")

        success = 0
        errors = 0
        start = time.time()

        for user in users.iterator():
            try:
                rebuild_user_state(user)
                success += 1
                self.stdout.write(f"  [{success}/{total}] {user.email} — OK")
            except Exception as e:
                errors += 1
                self.stderr.write(f"  [{success + errors}/{total}] {user.email} — ERROR: {e}")
                logger.error("SAE rebuild failed for %s: %s", user.email, e, exc_info=True)

        elapsed = round(time.time() - start, 1)
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {success} rebuilt, {errors} errors, {elapsed}s elapsed."
            )
        )
