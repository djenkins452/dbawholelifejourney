"""Capture app configuration."""

from django.apps import AppConfig


class CaptureConfig(AppConfig):
    """Configuration for the Capture app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.capture'
    verbose_name = 'Audio Capture'
