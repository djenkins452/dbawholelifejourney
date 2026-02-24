"""
Management command to enable/disable CoS v2 feature flag for users.

Usage:
    python manage.py cos_feature_flag --enable --user-email danny@example.com
    python manage.py cos_feature_flag --enable --all-users
    python manage.py cos_feature_flag --disable --user-email danny@example.com
    python manage.py cos_feature_flag --status                # Show current state
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Enable or disable the CoS v2 feature flag for users."

    def add_arguments(self, parser):
        action = parser.add_mutually_exclusive_group()
        action.add_argument(
            "--enable",
            action="store_true",
            help="Enable CoS v2 for specified users.",
        )
        action.add_argument(
            "--disable",
            action="store_true",
            help="Disable CoS v2 for specified users.",
        )
        action.add_argument(
            "--status",
            action="store_true",
            help="Show current feature flag status for all users.",
        )

        target = parser.add_mutually_exclusive_group()
        target.add_argument(
            "--user-email",
            type=str,
            help="Target a specific user by email.",
        )
        target.add_argument(
            "--user-id",
            type=int,
            help="Target a specific user by ID.",
        )
        target.add_argument(
            "--all-users",
            action="store_true",
            help="Target all users (use with --enable or --disable).",
        )

    def handle(self, *args, **options):
        if options["status"]:
            self._show_status()
            return

        if not options["enable"] and not options["disable"]:
            self.stderr.write(
                self.style.ERROR("Specify --enable, --disable, or --status.")
            )
            return

        enable = options["enable"]
        users = self._resolve_users(options)

        if not users:
            self.stderr.write(self.style.ERROR("No users found."))
            return

        count = 0
        for user in users:
            prefs = getattr(user, "preferences", None)
            if prefs:
                prefs.cos_v2_enabled = enable
                prefs.save(update_fields=["cos_v2_enabled"])
                count += 1
                action = "Enabled" if enable else "Disabled"
                self.stdout.write(f"  {action} CoS v2 for {user.email} (ID: {user.pk})")

        action = "Enabled" if enable else "Disabled"
        self.stdout.write(self.style.SUCCESS(
            f"\n{action} CoS v2 for {count} user(s)."
        ))

    def _resolve_users(self, options):
        """Resolve target users from command options."""
        if options.get("user_email"):
            try:
                return [User.objects.get(email=options["user_email"])]
            except User.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"User not found: {options['user_email']}")
                )
                return []

        if options.get("user_id"):
            try:
                return [User.objects.get(pk=options["user_id"])]
            except User.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"User not found: ID {options['user_id']}")
                )
                return []

        if options.get("all_users"):
            return list(User.objects.filter(is_active=True))

        self.stderr.write(
            self.style.ERROR("Specify --user-email, --user-id, or --all-users.")
        )
        return []

    def _show_status(self):
        """Show feature flag status for all users."""
        users = User.objects.filter(is_active=True).select_related("preferences")
        enabled = []
        disabled = []

        for user in users:
            prefs = getattr(user, "preferences", None)
            if prefs and getattr(prefs, "cos_v2_enabled", False):
                enabled.append(user)
            else:
                disabled.append(user)

        self.stdout.write(self.style.SUCCESS(f"\nCoS v2 ENABLED ({len(enabled)}):"))
        for user in enabled:
            self.stdout.write(f"  {user.email} (ID: {user.pk})")

        self.stdout.write(f"\nCoS v2 DISABLED ({len(disabled)}):")
        for user in disabled[:10]:  # Show first 10 to avoid spam
            self.stdout.write(f"  {user.email} (ID: {user.pk})")
        if len(disabled) > 10:
            self.stdout.write(f"  ... and {len(disabled) - 10} more")
