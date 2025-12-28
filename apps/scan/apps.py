"""Scan app configuration."""

from django.apps import AppConfig


class ScanConfig(AppConfig):
    """Configuration for the Scan app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scan'
    verbose_name = 'Camera Scan'
