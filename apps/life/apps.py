from django.apps import AppConfig


class LifeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.life"
    verbose_name = "Organize"

    def ready(self):
        """Import signals when the app is ready."""
        import apps.life.signals  # noqa: F401
