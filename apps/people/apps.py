"""
Whole Life Journey — Canonical Person domain app config.

`apps/people` is a foundational, always-on Layer 1 truth domain (peer of Medication,
Current Context, Execution, Mission Link). It is never feature-flagged.
"""

from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.people"
    verbose_name = "People (Canonical Person)"
