"""
Faith App Configuration
"""

from django.apps import AppConfig


class FaithConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.faith"
    verbose_name = "Faith"

    def ready(self):
        """Connect signals when the app is ready."""
        # Architecture Evolution Phase 1 — calendar projections
        import apps.faith.signals  # noqa: F401
