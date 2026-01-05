"""
Django App Configuration for WLJ Assistant Module.

Owner: admin@wholelifejourney.com
"""

from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """Configuration for the assistant app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assistant'
    verbose_name = 'Personal Assistant'
