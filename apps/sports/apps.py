"""
Sports Domain — AppConfig

Registers the sports app and imports signal handlers on ready.
"""
from django.apps import AppConfig


class SportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sports"
    verbose_name = "Sports"

    def ready(self):
        import apps.sports.signals  # noqa: F401
