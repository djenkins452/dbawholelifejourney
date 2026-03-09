from apps.core.domain_registry import registry
from apps.core.domain_registry.descriptors import DomainCapability

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
    related_domains=['goals', 'health'],
    url_namespace='life',
))
