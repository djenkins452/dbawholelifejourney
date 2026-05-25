"""
Journey App Configuration

Walking With God Through Scripture — isolated Journey feature.
Registered as its own Django app to keep migrations, admin, models, and
signals separate from the existing reading-plan system in apps/faith.
"""

from django.apps import AppConfig


class JourneyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.faith.journey"
    label = "journey"
    verbose_name = "Faith Journey"

    def ready(self):
        """Connect Journey signal handlers."""
        import apps.faith.journey.signals  # noqa: F401
