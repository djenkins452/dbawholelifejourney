"""
Run the HealthBriefing composer for one or more users and optionally
print the developer-facing explanation.

This command is the only Wave 3 entrypoint that exercises the composer
end-to-end. It is **not** wired to Beth or CoS — by design. Wave 5
adds the CoS slot and prompt addendum.

Usage:
    python manage.py run_health_briefing --user dannyjenkins71@gmail.com
    python manage.py run_health_briefing --user dannyjenkins71@gmail.com --no-persist
    python manage.py run_health_briefing --user dannyjenkins71@gmail.com --no-explain

Flags:
    --user <email>   Required. Compose for this user.
    --no-persist     Do not write a HealthBriefingSnapshot row.
    --no-explain     Suppress the developer-facing explanation output.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.core.health_briefing.composer import compose_briefing
from apps.core.health_briefing.explain import explain_briefing


User = get_user_model()


class Command(BaseCommand):
    help = "Run the HealthBriefing composer for a user (developer tool)."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=str, required=True)
        parser.add_argument(
            "--no-persist", action="store_true", default=False,
            help="Do not write a HealthBriefingSnapshot row.",
        )
        parser.add_argument(
            "--no-explain", action="store_true", default=False,
            help="Suppress the developer-facing explanation.",
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(email=options["user"])
        except User.DoesNotExist:
            raise CommandError(
                f"No user with email {options['user']!r}"
            )

        persist = not options["no_persist"]
        briefing = compose_briefing(user, persist=persist)

        if not options["no_explain"]:
            self.stdout.write(explain_briefing(briefing))
            self.stdout.write("")

        action = "persisted" if persist else "not persisted (--no-persist)"
        self.stdout.write(
            self.style.SUCCESS(
                f"Composed briefing {briefing.briefing_id[:12]}… for "
                f"user={user.email} ({action})."
            )
        )
