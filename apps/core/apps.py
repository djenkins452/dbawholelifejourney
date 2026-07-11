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
        # OPS-1 — connect Celery signals that record scheduled Beat-task runs
        # so the Ops Wall can detect MISSED_RUN for non-engine scheduled jobs.
        from apps.core.ai_observability.scheduled_task_monitor import (
            connect_signals as _connect_beat_task_signals,
        )
        _connect_beat_task_signals()
        # OPS-3 — connect chat-queue lifecycle signals (enqueue/start/complete)
        # so the Ops Wall can see chat backlog, stalls, and worker starvation.
        from apps.core.ai_observability.chat_queue_monitor import (
            connect_signals as _connect_chat_queue_signals,
        )
        _connect_chat_queue_signals()
        # WLJ Operations Phase II — register the recovery Celery task so Celery
        # discovers it (nested-subpackage tasks are not auto-discovered). Ships
        # dark: gated by OPS_RECOVERY_ENABLED (default False).
        import apps.core.operations.tasks  # noqa: F401
