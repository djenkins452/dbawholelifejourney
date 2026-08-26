# ==============================================================================
# File: apps/finance/management/commands/finance_reset.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Operator command to wipe Finance data before a first real connection.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Wipe all Finance operational and derived data. Dry-run by default.

    python manage.py finance_reset                       # inventory only, changes nothing
    python manage.py finance_reset --confirm RESET-FINANCE --by <staff email>

Refuses to run while any provider credential exists: deleting a live connection locally
would strand the provider's access with the only revocation credential destroyed.

Prints COUNTS ONLY. No amount, description, payee, account name, identifier, payload, or
token is read or displayed.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.finance.services.finance_reset import (
    ProviderCredentialPresent,
    inventory,
    invalidate_caches,
    reset,
)

CONFIRM_TOKEN = "RESET-FINANCE"


class Command(BaseCommand):
    help = "Permanently delete all Finance operational and derived data (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", help=f"Pass {CONFIRM_TOKEN} to actually delete.")
        parser.add_argument("--by", help="Email of the STAFF operator performing this.")

    def handle(self, *args, **options):
        User = get_user_model()

        before = inventory()
        self._render("BEFORE", before)

        provider = before["provider"]
        if provider["with_stored_token"] or provider["live_access"]:
            raise CommandError(
                f"{provider['with_stored_token']} connection(s) hold a provider token. "
                "Revoke them at the provider first — deleting locally would strand live "
                "access with no way to withdraw it."
            )

        if options.get("confirm") != CONFIRM_TOKEN:
            self.stdout.write(self.style.WARNING(
                f"\nDRY RUN — nothing deleted. Re-run with --confirm {CONFIRM_TOKEN} "
                "--by <staff email> to proceed."))
            return

        actor = None
        if options.get("by"):
            try:
                actor = User.objects.get(email__iexact=options["by"])
            except User.DoesNotExist:
                raise CommandError("Operator not found.")   # never echoes the address
            if not actor.is_staff:
                raise CommandError("Only a staff operator may reset Finance data.")

        try:
            result = reset(actor=actor)
        except ProviderCredentialPresent as exc:
            raise CommandError(str(exc))

        cleared = invalidate_caches(result["user_ids"])
        self.stdout.write(self.style.SUCCESS("\nRESET COMPLETE"))
        for key, count in sorted(result["removed"].items()):
            if count:
                self.stdout.write(f"  removed {key}: {count}")
        self.stdout.write(f"  caches invalidated for {cleared} user(s)")

        after = inventory()
        self._render("AFTER", after)

        # The reset's own audit record is PRESERVED evidence, not leftover data.
        audit_rows = after["finance_models"]["finance_audit_logs"]["total"]
        remaining = sum(v["total"] for key, v in after["finance_models"].items()
                        if key != "finance_audit_logs")
        remaining += sum(after["derived"].values())
        if remaining:
            self.stdout.write(self.style.WARNING(
                f"  {remaining} Finance record(s) remain — investigate."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"  Finance is empty ({audit_rows} redacted reset record retained as "
                "audit evidence)."))

    def _render(self, label, report):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{label} — redacted inventory"))
        for key, entry in report["finance_models"].items():
            extras = " ".join(f"{k}={v}" for k, v in entry.items() if k != "total")
            self.stdout.write(f"  {key:32} {entry['total']:>6}  {extras}")
        self.stdout.write("  -- derived --")
        for key, count in report["derived"].items():
            self.stdout.write(f"  {key:32} {count:>6}")
        self.stdout.write(
            f"  {'sae_state_rows_with_finance':32} "
            f"{report['state_rows_with_finance_key']:>6}")
        self.stdout.write("  -- preserved --")
        for key, count in report["preserved"].items():
            self.stdout.write(f"  {key:32} {count:>6}")
        self.stdout.write("  -- provider --")
        for key, count in report["provider"].items():
            self.stdout.write(f"  {key:32} {count:>6}")
