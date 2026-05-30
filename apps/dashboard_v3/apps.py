from django.apps import AppConfig


class DashboardV3Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard_v3"
    # User-visible name (Django admin app listing). Internal app `name` and
    # all internal references stay `dashboard_v3` for rollback safety.
    verbose_name = "Dashboard"
