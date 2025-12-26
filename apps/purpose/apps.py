"""
Purpose Module App Configuration
"""

from django.apps import AppConfig


class PurposeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.purpose'
    verbose_name = 'Purpose'
