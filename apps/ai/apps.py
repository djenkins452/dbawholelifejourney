from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai'
    verbose_name = 'AI Services'

    def ready(self):
        """Import signal handlers when app is ready."""
        from . import signals  # noqa: F401
