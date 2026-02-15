"""
Management command to run daily prediction generation.

Usage:
    python manage.py run_prediction_engine
"""

from django.core.management.base import BaseCommand

# Import rule modules so they register with the prediction registry
import apps.core.ai_predictions.prediction_rules_health  # noqa: F401
import apps.core.ai_predictions.prediction_rules_bodycomp  # noqa: F401
import apps.core.ai_predictions.prediction_rules_goals  # noqa: F401
import apps.core.ai_predictions.prediction_rules_habits  # noqa: F401
import apps.core.ai_predictions.prediction_rules_labs  # noqa: F401

from apps.core.ai_predictions.scheduler import run_predictions_all_users


class Command(BaseCommand):
    help = "Run daily prediction generation for all active users"

    def handle(self, *args, **options):
        self.stdout.write("Running prediction engine...")
        total = run_predictions_all_users()
        self.stdout.write(self.style.SUCCESS(f"Generated {total} predictions."))
