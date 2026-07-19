"""Capture app configuration."""

from django.apps import AppConfig


class CaptureConfig(AppConfig):
    """Configuration for the Capture app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.capture'
    verbose_name = 'Audio Capture'

    def ready(self):
        # Self-register the DomainTruth providers this app owns, so registration
        # does not depend on editing the central provider list in
        # apps/core/truth/domain.py (a hot, cross-cutting file). Importing the
        # module runs its @register_domain_truth decorators. Never fatal.
        for mod in (
            "apps.capture.services.capture_domain_truth",
            "apps.capture.services.artifact_domain_truth",  # Artifacts as Truth
        ):
            try:
                __import__(mod)
            except Exception:  # pragma: no cover - registration must not break startup
                import logging
                logging.getLogger(__name__).warning(
                    "capture: failed to import truth provider %s", mod, exc_info=True)
