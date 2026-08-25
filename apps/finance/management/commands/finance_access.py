# ==============================================================================
# File: apps/finance/management/commands/finance_access.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Controlled staff path for granting/revoking Finance (provider) access.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Grant Finance access to a user Danny has explicitly approved.

Finance — and therefore any provider/bank connection — is an explicitly granted
capability. Signing up does not confer it, and nothing enables it in bulk. **No identity
is hardcoded anywhere**: this command takes whichever email the operator names.

    python manage.py finance_access --list
    python manage.py finance_access --grant person@example.com --by admin@example.com
    python manage.py finance_access --revoke person@example.com --by admin@example.com

`--by` must be a staff account; the grant is refused otherwise.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.finance.access import grant_finance_access, revoke_finance_access


class Command(BaseCommand):
    help = "Grant, revoke, or list explicit Finance access."

    def add_arguments(self, parser):
        parser.add_argument("--grant", help="Email of the user to enable.")
        parser.add_argument("--revoke", help="Email of the user to disable.")
        parser.add_argument("--by", help="Email of the STAFF user performing this.")
        parser.add_argument("--list", action="store_true",
                            help="Report the aggregate count of enabled users.")

    def handle(self, *args, **options):
        User = get_user_model()

        if options.get("list"):
            total = User.objects.count()
            enabled = User.objects.filter(preferences__finances_enabled=True).count()
            self.stdout.write(self.style.SUCCESS(
                f"Finance-enabled users: {enabled} of {total}"))
            return

        target_email = options.get("grant") or options.get("revoke")
        if not target_email:
            raise CommandError("Use --grant, --revoke, or --list.")
        if not options.get("by"):
            raise CommandError("--by <staff email> is required and is recorded.")

        try:
            target = User.objects.get(email__iexact=target_email)
            actor = User.objects.get(email__iexact=options["by"])
        except User.DoesNotExist:
            raise CommandError("User not found.")     # never echoes the address back

        if options.get("grant"):
            grant_finance_access(target, granted_by=actor)
            self.stdout.write(self.style.SUCCESS("Finance access GRANTED."))
        else:
            revoke_finance_access(target, revoked_by=actor)
            self.stdout.write(self.style.SUCCESS(
                "Finance access REVOKED. Existing provider connections are NOT revoked "
                "by this — disconnect them explicitly."))
