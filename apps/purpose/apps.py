"""
Purpose Module App Configuration
"""

from django.apps import AppConfig


class PurposeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.purpose'
    verbose_name = 'Goals'

    def ready(self):
        """Import signals when the app is ready."""
        import apps.purpose.signals  # noqa: F401
