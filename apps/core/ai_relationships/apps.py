"""
AI Relationships App Configuration
"""

from django.apps import AppConfig


class AiRelationshipsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core.ai_relationships"
    label = "ai_relationships"
    verbose_name = "AI Relationships"
