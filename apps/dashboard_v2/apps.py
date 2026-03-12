from django.apps import AppConfig


class DashboardV2Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard_v2"
    verbose_name = "Dashboard V2"

    def ready(self):
        from . import signals  # noqa: F401
