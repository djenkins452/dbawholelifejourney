"""
Health App Configuration
"""

from django.apps import AppConfig


class HealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health"
    verbose_name = "Health"

    def ready(self):
        """Connect signals when the app is ready."""
        from django.db.models.signals import post_save
        from .models import CycleDailyLog
        from .services.cycle_detection import process_daily_log_signal

        post_save.connect(
            process_daily_log_signal,
            sender=CycleDailyLog,
            dispatch_uid="cycle_daily_log_detection"
        )

        # Architecture Evolution Phase 1 — calendar projections
        import apps.health.signals  # noqa: F401
