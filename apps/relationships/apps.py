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
        # Extend the canonical Person domain via its hook seam — Core never imports this
        # feature app. (1) hover-card facts; (2) deterministic relationship-derived
        # recognition ("my wife" → the canonical spouse), as read-only projections.
        from apps.people.services.hooks import (
            register_person_roles_provider,
            register_person_summary_provider,
            register_role_phrases_provider,
            register_role_resolver,
        )
        from .person_summary import relationship_person_summary
        from .relationship_recognition import (
            all_role_phrases, person_role_phrases, resolve_relationship_role,
        )
        register_person_summary_provider(relationship_person_summary)
        register_role_resolver(resolve_relationship_role)
        register_person_roles_provider(person_role_phrases)
        register_role_phrases_provider(all_role_phrases)
