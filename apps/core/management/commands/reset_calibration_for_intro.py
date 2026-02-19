"""
One-time reset: ALL users' calibration and chat history for the new
data-aware introduction flow. Uses DataLoadConfig tracking so it only
runs once.

Usage:
    python manage.py reset_calibration_for_intro
    python manage.py reset_calibration_for_intro --dry-run
    python manage.py reset_calibration_for_intro --force
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


TRACKER_NAME = 'reset_calibration_data_aware_intro_v2'


class Command(BaseCommand):
    help = "Reset all users' calibration for the new data-aware intro flow"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Show what would be reset without changing anything",
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help="Run even if already marked complete",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        # Check if already run (one-time guard)
        try:
            from apps.admin_console.models import DataLoadConfig
            tracker = DataLoadConfig.objects.filter(name=TRACKER_NAME).first()
            if tracker and tracker.is_loaded and not force:
                self.stdout.write("  Calibration intro reset already done. "
                                  "Use --force to re-run.")
                return
        except Exception:
            pass  # No tracker model = first run

        try:
            from apps.core.blueprint.models import PersonalOperatingBlueprint
        except ImportError:
            self.stdout.write(self.style.ERROR("Blueprint model not found"))
            return

        blueprints = PersonalOperatingBlueprint.objects.select_related(
            'user').all()
        reset_count = 0

        for bp in blueprints:
            user = bp.user
            overrides = bp.governance_overrides or {}

            if dry_run:
                self.stdout.write(
                    f"  Would reset: {user.email} "
                    f"(stage={overrides.get('calibration_stage', 'N/A')}, "
                    f"welcome={overrides.get('calibration_welcome_shown', 'N/A')}, "
                    f"complete={bp.calibration_complete})"
                )
                reset_count += 1
                continue

            bp.calibration_complete = False
            overrides['calibration_stage'] = 0
            overrides['calibration_paused'] = False
            overrides['calibration_welcome_shown'] = False
            overrides['calibration_answers'] = {}
            overrides['calibration_complete'] = False
            overrides['calibration_intro_reset_at'] = (
                timezone.now().isoformat()
            )
            bp.governance_overrides = overrides
            bp.save(update_fields=[
                'calibration_complete', 'governance_overrides',
                'updated_at',
            ])

            # Clear chat history
            try:
                from apps.ai.models import AssistantConversation
                conv = AssistantConversation.objects.filter(
                    user=user, is_active=True).first()
                if conv:
                    msg_count = conv.messages.count()
                    conv.messages.all().delete()
                    self.stdout.write(
                        f"  Reset: {user.email} "
                        f"(cleared {msg_count} messages)"
                    )
                else:
                    self.stdout.write(f"  Reset: {user.email} (no conv)")
            except Exception as e:
                self.stdout.write(
                    f"  Reset: {user.email} (chat clear failed: {e})")

            reset_count += 1

        # Mark as done so it doesn't re-run
        if not dry_run:
            try:
                from apps.admin_console.models import DataLoadConfig
                DataLoadConfig.objects.update_or_create(
                    name=TRACKER_NAME,
                    defaults={
                        'is_loaded': True,
                        'description': (
                            f'Reset {reset_count} users for data-aware '
                            f'calibration intro'
                        ),
                    }
                )
            except Exception:
                pass

        action = "Would reset" if dry_run else "Reset"
        self.stdout.write(
            self.style.SUCCESS(f"\n{action}: {reset_count} user(s).")
        )
