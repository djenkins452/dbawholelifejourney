"""
Life Module - Recurrence Service

Handles recurring tasks and events with human-friendly patterns.
Supports: daily, weekly, biweekly, monthly, yearly, and custom patterns.
"""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.db import transaction


# =============================================================================
# Recurrence Pattern Parser
# =============================================================================

class RecurrencePattern:
    """
    Parse and work with recurrence patterns.
    
    Supported patterns:
    - daily
    - weekly
    - biweekly
    - monthly
    - yearly
    - every_weekday (Mon-Fri)
    - weekly:mon,wed,fri (specific days)
    - monthly:15 (specific day of month)
    - monthly:last (last day of month)
    - monthly:first_monday (first Monday of month)
    """
    
    WEEKDAYS = {
        'mon': 0, 'monday': 0,
        'tue': 1, 'tuesday': 1,
        'wed': 2, 'wednesday': 2,
        'thu': 3, 'thursday': 3,
        'fri': 4, 'friday': 4,
        'sat': 5, 'saturday': 5,
        'sun': 6, 'sunday': 6,
    }
    
    def __init__(self, pattern_string):
        self.pattern_string = pattern_string.lower().strip()
        self.pattern_type = None
        self.interval = 1
        self.weekdays = []
        self.day_of_month = None
        self.week_of_month = None
        
        self._parse()
    
    def _parse(self):
        """Parse the pattern string into components."""
        pattern = self.pattern_string
        
        if pattern == 'daily':
            self.pattern_type = 'daily'
        
        elif pattern == 'weekly':
            self.pattern_type = 'weekly'
        
        elif pattern == 'biweekly':
            self.pattern_type = 'weekly'
            self.interval = 2
        
        elif pattern == 'monthly':
            self.pattern_type = 'monthly'
        
        elif pattern == 'yearly' or pattern == 'annually':
            self.pattern_type = 'yearly'
        
        elif pattern == 'every_weekday' or pattern == 'weekdays':
            self.pattern_type = 'weekly'
            self.weekdays = [0, 1, 2, 3, 4]  # Mon-Fri
        
        elif pattern.startswith('weekly:'):
            # Parse specific weekdays: weekly:mon,wed,fri
            self.pattern_type = 'weekly'
            days_str = pattern.split(':', 1)[1]
            for day in days_str.split(','):
                day = day.strip()
                if day in self.WEEKDAYS:
                    self.weekdays.append(self.WEEKDAYS[day])
        
        elif pattern.startswith('monthly:'):
            self.pattern_type = 'monthly'
            spec = pattern.split(':', 1)[1].strip()
            
            if spec == 'last':
                self.day_of_month = 'last'
            elif spec.isdigit():
                self.day_of_month = int(spec)
            elif '_' in spec:
                # e.g., first_monday, second_tuesday, last_friday
                parts = spec.split('_')
                if len(parts) == 2:
                    ordinal, weekday = parts
                    ordinals = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'last': -1}
                    if ordinal in ordinals and weekday in self.WEEKDAYS:
                        self.week_of_month = ordinals[ordinal]
                        self.weekdays = [self.WEEKDAYS[weekday]]
        
        elif pattern.startswith('every_'):
            # Parse interval patterns: every_2_days, every_3_weeks
            parts = pattern.split('_')
            if len(parts) == 3 and parts[1].isdigit():
                self.interval = int(parts[1])
                unit = parts[2]
                if unit in ('day', 'days'):
                    self.pattern_type = 'daily'
                elif unit in ('week', 'weeks'):
                    self.pattern_type = 'weekly'
                elif unit in ('month', 'months'):
                    self.pattern_type = 'monthly'
                elif unit in ('year', 'years'):
                    self.pattern_type = 'yearly'
    
    def get_next_occurrence(self, from_date):
        """
        Calculate the next occurrence after from_date.
        
        Args:
            from_date: The reference date (usually today or task due date)
        
        Returns:
            The next occurrence date, or None if pattern is invalid
        """
        if not self.pattern_type:
            return None
        
        if isinstance(from_date, str):
            from_date = date.fromisoformat(from_date)
        
        if self.pattern_type == 'daily':
            return from_date + timedelta(days=self.interval)
        
        elif self.pattern_type == 'weekly':
            if self.weekdays:
                # Find next matching weekday
                next_date = from_date + timedelta(days=1)
                for _ in range(14):  # Check up to 2 weeks
                    if next_date.weekday() in self.weekdays:
                        return next_date
                    next_date += timedelta(days=1)
                return from_date + timedelta(weeks=self.interval)
            else:
                return from_date + timedelta(weeks=self.interval)
        
        elif self.pattern_type == 'monthly':
            if self.day_of_month == 'last':
                # Last day of next month
                next_month = from_date + relativedelta(months=self.interval)
                next_month = next_month.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
                return next_month
            
            elif self.day_of_month:
                # Specific day of month
                next_month = from_date + relativedelta(months=self.interval)
                try:
                    return next_month.replace(day=self.day_of_month)
                except ValueError:
                    # Day doesn't exist in that month (e.g., Feb 31)
                    # Use last day of month instead
                    next_month = next_month.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
                    return next_month
            
            elif self.week_of_month and self.weekdays:
                # e.g., First Monday of month
                next_month = from_date + relativedelta(months=self.interval)
                first_of_month = next_month.replace(day=1)
                target_weekday = self.weekdays[0]
                
                if self.week_of_month == -1:  # Last occurrence
                    # Start from end of month
                    last_of_month = first_of_month + relativedelta(months=1) - timedelta(days=1)
                    current = last_of_month
                    while current.weekday() != target_weekday:
                        current -= timedelta(days=1)
                    return current
                else:
                    # Find nth occurrence
                    current = first_of_month
                    while current.weekday() != target_weekday:
                        current += timedelta(days=1)
                    # Add weeks for nth occurrence
                    current += timedelta(weeks=self.week_of_month - 1)
                    return current
            
            else:
                # Same day next month
                return from_date + relativedelta(months=self.interval)
        
        elif self.pattern_type == 'yearly':
            return from_date + relativedelta(years=self.interval)
        
        return None
    
    def get_occurrences(self, start_date, end_date, max_count=100):
        """
        Generate all occurrences between start_date and end_date.
        
        Args:
            start_date: Start of range
            end_date: End of range
            max_count: Maximum occurrences to return (safety limit)
        
        Returns:
            List of dates
        """
        occurrences = []
        current = start_date
        
        while current <= end_date and len(occurrences) < max_count:
            occurrences.append(current)
            next_date = self.get_next_occurrence(current)
            if not next_date or next_date <= current:
                break
            current = next_date
        
        return occurrences


# =============================================================================
# Recurrence Service
# =============================================================================

class RecurrenceService:
    """
    Service for managing recurring tasks and events.
    """
    
    @staticmethod
    def process_completed_recurring_task(task):
        """
        When a recurring task is completed, create the next occurrence.
        
        Args:
            task: The completed Task instance
        
        Returns:
            The newly created Task for next occurrence, or None
        """
        if not task.is_recurring or not task.recurrence_pattern:
            return None
        
        pattern = RecurrencePattern(task.recurrence_pattern)
        base_date = task.due_date or timezone.now().date()
        next_date = pattern.get_next_occurrence(base_date)
        
        if not next_date:
            return None
        
        # Import here to avoid circular imports
        from apps.life.models import Task
        
        # Create new task for next occurrence
        with transaction.atomic():
            new_task = Task.objects.create(
                user=task.user,
                title=task.title,
                notes=task.notes,
                project=task.project,
                priority=task.priority,
                effort=task.effort,
                due_date=next_date,
                is_recurring=True,
                recurrence_pattern=task.recurrence_pattern,
            )
        
        return new_task
    
    @staticmethod
    def generate_recurring_events(event, start_date, end_date):
        """
        Generate virtual event instances for a recurring event.
        
        This doesn't create database records - it returns a list of
        event-like dictionaries for display purposes.
        
        Args:
            event: The recurring LifeEvent instance
            start_date: Start of range to generate
            end_date: End of range to generate
        
        Returns:
            List of event dictionaries with adjusted dates
        """
        if not event.is_recurring or not event.recurrence_pattern:
            return []
        
        pattern = RecurrencePattern(event.recurrence_pattern)
        
        # Respect recurrence end date if set
        if event.recurrence_end_date and event.recurrence_end_date < end_date:
            end_date = event.recurrence_end_date
        
        occurrences = pattern.get_occurrences(event.start_date, end_date)
        
        # Filter to requested range
        occurrences = [d for d in occurrences if d >= start_date]
        
        events = []
        for occurrence_date in occurrences:
            # Calculate offset from original date
            date_offset = occurrence_date - event.start_date
            
            event_data = {
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'event_type': event.event_type,
                'start_date': occurrence_date,
                'start_time': event.start_time,
                'end_date': event.end_date + date_offset if event.end_date else None,
                'end_time': event.end_time,
                'is_all_day': event.is_all_day,
                'location': event.location,
                'is_recurring': True,
                'is_virtual': True,  # Flag that this is a generated instance
                'parent_event': event,
                'get_event_type_display': event.get_event_type_display,
            }
            events.append(event_data)
        
        return events
    
    @staticmethod
    def get_events_for_range(user, start_date, end_date):
        """
        Get all events (regular and recurring) for a date range.
        
        Args:
            user: The user
            start_date: Start of range
            end_date: End of range
        
        Returns:
            List of events and virtual recurring event instances
        """
        from django.db.models import Q
        from apps.life.models import LifeEvent
        
        # Get non-recurring events in range
        regular_events = list(LifeEvent.objects.filter(
            user=user,
            is_recurring=False,
            start_date__gte=start_date,
            start_date__lte=end_date
        ))
        
        # Get recurring events that could have instances in range
        # (started before or during the range)
        recurring_events = LifeEvent.objects.filter(
            user=user,
            is_recurring=True,
            start_date__lte=end_date
        ).filter(
            Q(recurrence_end_date__isnull=True) | 
            Q(recurrence_end_date__gte=start_date)
        )
        
        # Generate virtual instances for recurring events
        all_events = regular_events.copy()
        
        for event in recurring_events:
            virtual_instances = RecurrenceService.generate_recurring_events(
                event, start_date, end_date
            )
            all_events.extend(virtual_instances)
        
        # Sort by date and time
        all_events.sort(key=lambda e: (
            e.start_date if hasattr(e, 'start_date') else e['start_date'],
            e.start_time if hasattr(e, 'start_time') else e.get('start_time') or ''
        ))
        
        return all_events


# =============================================================================
# Management Command Helper
# =============================================================================

def process_overdue_recurring_tasks():
    """
    Process all overdue recurring tasks and create next occurrences.
    
    This can be run as a daily cron job or management command.
    
    Returns:
        Number of new tasks created
    """
    from apps.life.models import Task
    
    today = timezone.now().date()
    
    # Find completed recurring tasks that need a new instance
    completed_recurring = Task.objects.filter(
        is_recurring=True,
        is_completed=True,
        recurrence_pattern__isnull=False
    ).exclude(
        recurrence_pattern=''
    )
    
    created_count = 0
    
    for task in completed_recurring:
        # Check if a future task already exists with same title/pattern
        future_exists = Task.objects.filter(
            user=task.user,
            title=task.title,
            is_recurring=True,
            is_completed=False,
            due_date__gte=today
        ).exists()
        
        if not future_exists:
            new_task = RecurrenceService.process_completed_recurring_task(task)
            if new_task:
                created_count += 1
    
    return created_count