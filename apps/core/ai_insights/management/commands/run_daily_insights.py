"""
Management command to run daily insight checks for all active users.

Usage:
    python manage.py run_daily_insights
"""

from django.core.management.base import BaseCommand

from apps.core.ai_insights.scheduler import run_daily_insights_all_users


class Command(BaseCommand):
    help = "Run daily proactive insight checks for all active users"

    def handle(self, *args, **options):
        self.stdout.write("Running daily insights...")

        # Import rule modules to ensure they're registered
        import apps.core.ai_insights.rules_health  # noqa: F401
        import apps.core.ai_insights.rules_body_composition  # noqa: F401
        import apps.core.ai_insights.rules_labs_vitals  # noqa: F401
        import apps.core.ai_insights.rules_goals  # noqa: F401
        import apps.core.ai_insights.rules_habits  # noqa: F401
        import apps.core.ai_insights.rules_scripture  # noqa: F401
        import apps.core.ai_insights.rules_journal  # noqa: F401
        import apps.core.ai_insights.rules_meals  # noqa: F401

        total = run_daily_insights_all_users()
        self.stdout.write(
            self.style.SUCCESS(f"Daily insights complete: {total} insights generated")
        )
