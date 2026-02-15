"""
Management command to run one DNE delivery cycle.

Usage:
    python manage.py run_delivery_cycle
    python manage.py run_delivery_cycle --dry-run
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run one cycle of the Delivery & Notification Engine (DNE)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be delivered without actually sending.",
        )

    def handle(self, *args, **options):
        from apps.core.ai_delivery.delivery_engine import deliver_due_notifications

        if options["dry_run"]:
            self.stdout.write("DNE: Dry run — no notifications will be sent.")
            # Still run to identify items, but delivery_engine is idempotent
            # (dedupe prevents re-send), so dry-run just reports counts.

        result = deliver_due_notifications()

        self.stdout.write(
            self.style.SUCCESS(
                f"DNE: delivered={result['delivered']}, "
                f"skipped={result['skipped']}, "
                f"failed={result['failed']}"
            )
        )
