# ==============================================================================
# File: apps/finance/management/commands/seed_finance_categories.py
# Description: Seed the globally-safe WLJ spending taxonomy. Idempotent.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Create the global WLJ category taxonomy (`user=None, is_system=True`).

Replaces `load_default_categories`, which created every row with `user=<a user>` AND
`is_system=True`. Because `get_for_user` matches on either, those rows became visible to
EVERY user — one person's classifications leaking into everyone's list, duplicated once
per account. This command creates categories owned by nobody, which is what "system"
should have meant.

    python manage.py seed_finance_categories             # idempotent
    python manage.py seed_finance_categories --dry-run
"""
from django.core.management.base import BaseCommand

from apps.finance.services.category_taxonomy import (
    SYSTEM_CATEGORIES,
    seed_system_categories,
)


class Command(BaseCommand):
    help = "Seed the global WLJ transaction category taxonomy (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from apps.finance.models import TransactionCategory

        before_global = TransactionCategory.objects.filter(
            user__isnull=True, is_system=True).count()
        leaky = TransactionCategory.objects.filter(
            user__isnull=False, is_system=True).count()

        self.stdout.write(f"Global system categories before: {before_global}")
        self.stdout.write(f"Defined in the taxonomy:         {len(SYSTEM_CATEGORIES)}")
        if leaky:
            self.stdout.write(self.style.WARNING(
                f"{leaky} user-owned row(s) are flagged is_system=True and are visible "
                "to every user. They are NOT touched here; review them separately."))

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("DRY RUN — nothing created."))
            return

        created, existing = seed_system_categories()
        after = TransactionCategory.objects.filter(
            user__isnull=True, is_system=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"created={created} already_present={existing} total_global={after}"))
        if created == 0:
            self.stdout.write("Already seeded — no changes.")
