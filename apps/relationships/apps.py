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
        # Contribute relationship label + rich person-page URL to the shared canonical
        # Person hover card, without Core ever importing this feature app.
        from apps.people.services.hooks import register_person_summary_provider
        from .person_summary import relationship_person_summary
        register_person_summary_provider(relationship_person_summary)
