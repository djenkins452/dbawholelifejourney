"""
EAE App Configuration
"""

from django.apps import AppConfig


class AiEaeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core.ai_eae"
    label = "ai_eae"
    verbose_name = "Executive Arbitration Engine"
