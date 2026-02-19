"""
One-time management command to reset calibration for existing users
who completed the old 14-day trickle system but never did
conversational onboarding.

Usage:
    python manage.py reset_calibration_conversational --dry-run
    python manage.py reset_calibration_conversational
"""

from django.core.management.base import BaseCommand

from apps.core.blueprint.cos_governance import reset_calibration_for_conversational
from apps.core.blueprint.models import PersonalOperatingBlueprint


class Command(BaseCommand):
    help = "Reset calibration for users who completed the old 14-day trickle system"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Show what would be reset without actually changing anything",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        blueprints = PersonalOperatingBlueprint.objects.filter(
            calibration_complete=True,
        ).select_related('user')

        reset_count = 0
        skip_count = 0

        for bp in blueprints:
            overrides = bp.governance_overrides or {}
            if 'calibration_stage' not in overrides:
                if dry_run:
                    self.stdout.write(
                        f"  Would reset: {bp.user.email} "
                        f"(day={bp.calibration_day})"
                    )
                else:
                    result = reset_calibration_for_conversational(bp.user)
                    if result:
                        self.stdout.write(
                            f"  Reset: {bp.user.email}"
                        )
                reset_count += 1
            else:
                skip_count += 1

        action = "Would reset" if dry_run else "Reset"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{action}: {reset_count} user(s). "
                f"Skipped (already new system): {skip_count}."
            )
        )
