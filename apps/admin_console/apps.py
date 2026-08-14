from django.apps import AppConfig


class AdminConsoleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admin_console"

    def ready(self):
        # TEMPORARY — register the multi-domain evidence A/B experiment task on the
        # worker (autodiscovery only scans <app>/tasks.py). REMOVE with the experiment.
        try:
            from apps.admin_console import _analysis_ab_experiment  # noqa: F401
        except Exception:
            pass
