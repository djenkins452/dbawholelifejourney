"""
Whole Life Journey - Relationships App Configuration

Project: Whole Life Journey
Path: apps/relationships/apps.py
Purpose: Django app config for Relational Intelligence platform

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.apps import AppConfig


class RelationshipsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.relationships"
    verbose_name = "Relationships"

    def ready(self):
        import apps.relationships.signals  # noqa: F401
