"""
Whole Life Journey - Core App Configuration

Project: Whole Life Journey
Path: apps/core/apps.py
Purpose: Django app configuration for the core module

Description:
    Standard Django app configuration class for the core application.
    Registers the app with Django and sets the verbose name for admin.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Register Phase 4 pressure signals
        import apps.core.blueprint.pressure_signals  # noqa: F401
        # Register Phase 5 protective action signals
        import apps.core.blueprint.protective_signals  # noqa: F401
        # Domain Capability Registry — auto-discover all domain capabilities
        from apps.core.domain_registry import autodiscover
        autodiscover()
        # Enhance all NumberInput widgets with mobile-friendly inputmode
        from apps.core.widgets import enhance_number_inputs
        enhance_number_inputs()
        # Register domain event subscribers for intelligence pipeline
        import apps.core.events.subscribers  # noqa: F401
        # Register execution quality signal handlers
        import apps.core.signals.execution_signals  # noqa: F401
        # Phase 1A · C12 — register HealthBriefing shared_task definitions
        # and event-triggered recompute signal handlers.
        import apps.core.health_briefing.tasks  # noqa: F401
        import apps.core.health_briefing.signals  # noqa: F401
