from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability, DomainClass

registry.register(DomainCapability(
    name='life',
    display_name='Organize (Tasks & Calendar)',
    description='Tasks, routines, calendar events, reminders, and life organization',
    intent_types=[
        'create_task', 'create_routine_task', 'complete_task', 'skip_task',
        'read_task', 'mutate_task', 'create_event', 'mutate_calendar_event',
        'add_reminder',
    ],
    primary_models=['Task', 'CalendarEvent', 'Reminder', 'SignificantEvent'],
    context_builders=['_build_plan_and_alignment', '_build_pressure_and_deadlines'],
    proactive_signals=[
        'task_overdue', 'event_approaching', 'nn_skip_streak',
        'busy_day_upcoming', 'task_repeatedly_postponed',
    ],
    expected_signal_types=['productivity_progress'],
    related_domains=['goals', 'health'],
    url_namespace='life',
))

# Documents is a knowledge-layer domain — file/record storage with metadata.
# It does NOT emit behavioral signals or support CoS intents today.
# Registered truthfully as knowledge class to prevent fake architecture.
registry.register(DomainCapability(
    name='documents',
    display_name='Documents',
    description='Important document storage and organization (insurance, legal, medical records)',
    domain_class=DomainClass.KNOWLEDGE,
    intent_types=[],
    primary_models=['Document'],
    context_builders=[],
    proactive_signals=['document_expiring'],
    related_domains=['life', 'medical'],
    url_namespace='life',
))
