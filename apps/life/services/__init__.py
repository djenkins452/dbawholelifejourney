"""
Life Module Services

Business logic and external integrations.
"""

from .recurrence import RecurrencePattern, RecurrenceService, process_overdue_recurring_tasks

__all__ = [
    'RecurrencePattern',
    'RecurrenceService', 
    'process_overdue_recurring_tasks',
]