"""
Calendar Engine Models

Unified calendar/event system for Whole Life Journey.
Provides projection layer over Tasks, Goals, Habits + manual events.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class CalendarEvent(models.Model):
    """
    Unified calendar event. Can be manual or projected from a source
    (Task, Goal, Habit, LifeEvent).
    """

    # Event kinds
    KIND_MANUAL = 'manual'
    KIND_DEADLINE_MARKER = 'deadline_marker'
    KIND_EXECUTION_BLOCK = 'execution_block'
    KIND_EXTERNAL_READONLY = 'external_readonly'

    EVENT_KIND_CHOICES = [
        (KIND_MANUAL, 'Manual'),
        (KIND_DEADLINE_MARKER, 'Deadline Marker'),
        (KIND_EXECUTION_BLOCK, 'Execution Block'),
        (KIND_EXTERNAL_READONLY, 'External (Read-Only)'),
    ]

    # Source types for projection tracking
    SOURCE_NONE = 'none'
    SOURCE_TASK = 'task'
    SOURCE_GOAL = 'goal'
    SOURCE_GOAL_MILESTONE = 'goal_milestone'
    SOURCE_HABIT = 'habit'
    SOURCE_LIFE_EVENT = 'life_event'
    SOURCE_EXTERNAL = 'external'

    SOURCE_TYPE_CHOICES = [
        (SOURCE_NONE, 'None (Manual)'),
        (SOURCE_TASK, 'Task'),
        (SOURCE_GOAL, 'Goal'),
        (SOURCE_GOAL_MILESTONE, 'Goal Milestone'),
        (SOURCE_HABIT, 'Habit'),
        (SOURCE_LIFE_EVENT, 'Life Event'),
        (SOURCE_EXTERNAL, 'External'),
    ]

    # Status
    STATUS_SCHEDULED = 'scheduled'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELED = 'canceled'

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_events',
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    is_all_day = models.BooleanField(default=False)

    domain = models.ForeignKey(
        'purpose.LifeDomain',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events',
    )

    event_kind = models.CharField(
        max_length=20,
        choices=EVENT_KIND_CHOICES,
        default=KIND_MANUAL,
    )
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        default=SOURCE_NONE,
    )
    source_id = models.CharField(
        max_length=100,
        blank=True,
        help_text='PK of the source object (stored as string for flexibility)',
    )

    is_protected = models.BooleanField(
        default=False,
        help_text='Used by Habit Protection Layer — prevents silent overwrites',
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
    )

    idempotency_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text='SHA-256 hash for assistant-path duplicate prevention',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_dt']
        indexes = [
            models.Index(fields=['user', 'start_dt']),
            models.Index(fields=['user', 'source_type', 'source_id']),
            models.Index(fields=['user', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'title', 'start_dt'],
                name='unique_user_title_start',
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_event_kind_display()}) - {self.start_dt:%Y-%m-%d}"

    @property
    def is_projected(self):
        """True if this event is linked to a source object."""
        return self.source_type != self.SOURCE_NONE

    @property
    def duration_minutes(self):
        """Duration in minutes."""
        delta = self.end_dt - self.start_dt
        return int(delta.total_seconds() / 60)


class RecurrenceRule(models.Model):
    """
    Recurrence rule attached to a CalendarEvent.
    Occurrences are rendered dynamically — no row-per-occurrence.
    """

    FREQ_DAILY = 'daily'
    FREQ_WEEKLY = 'weekly'
    FREQ_MONTHLY = 'monthly'

    FREQUENCY_CHOICES = [
        (FREQ_DAILY, 'Daily'),
        (FREQ_WEEKLY, 'Weekly'),
        (FREQ_MONTHLY, 'Monthly'),
    ]

    event = models.OneToOneField(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name='recurrence',
    )
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    byweekday = models.JSONField(
        default=list,
        blank=True,
        help_text='List of ISO weekday numbers (1=Mon..7=Sun)',
    )
    interval = models.PositiveIntegerField(default=1)
    until_dt = models.DateTimeField(null=True, blank=True)
    count = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='America/Chicago')

    def __str__(self):
        return f"Recurrence: {self.get_frequency_display()} for {self.event.title}"

    def get_occurrences(self, range_start, range_end):
        """
        Generate occurrence datetimes within the given range.
        Returns list of (start_dt, end_dt) tuples.
        """
        import datetime as dt

        occurrences = []
        event_duration = self.event.end_dt - self.event.start_dt
        current = self.event.start_dt

        # Cap iterations for safety
        max_iterations = 1000
        iteration = 0
        generated = 0

        while current <= range_end and iteration < max_iterations:
            iteration += 1

            # Check count limit
            if self.count is not None and generated >= self.count:
                break
            # Check until limit
            if self.until_dt is not None and current > self.until_dt:
                break

            if current >= range_start:
                # Check byweekday filter
                if self.byweekday:
                    iso_weekday = current.isoweekday()
                    if iso_weekday not in self.byweekday:
                        current = self._advance(current)
                        continue

                occurrences.append((current, current + event_duration))
                generated += 1

            current = self._advance(current)

        return occurrences

    def _advance(self, current_dt):
        """Advance to next potential occurrence based on frequency + interval."""
        import datetime as dt

        if self.frequency == self.FREQ_DAILY:
            return current_dt + dt.timedelta(days=self.interval)
        elif self.frequency == self.FREQ_WEEKLY:
            if self.byweekday:
                # Advance day-by-day to find next matching weekday
                next_dt = current_dt + dt.timedelta(days=1)
                days_checked = 0
                while days_checked < 7 * self.interval:
                    if next_dt.isoweekday() in self.byweekday:
                        return next_dt
                    next_dt += dt.timedelta(days=1)
                    days_checked += 1
                # Fallback
                return current_dt + dt.timedelta(weeks=self.interval)
            return current_dt + dt.timedelta(weeks=self.interval)
        elif self.frequency == self.FREQ_MONTHLY:
            month = current_dt.month + self.interval
            year = current_dt.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current_dt.day, 28)
            return current_dt.replace(year=year, month=month, day=day)
        return current_dt + dt.timedelta(days=1)


class RecurrenceException(models.Model):
    """
    Exception to a recurrence rule — used when a single occurrence
    is moved or canceled without changing the whole series.
    """

    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name='recurrence_exceptions',
    )
    original_start_dt = models.DateTimeField(
        help_text='The original occurrence start that this exception replaces',
    )
    new_start_dt = models.DateTimeField(null=True, blank=True)
    new_end_dt = models.DateTimeField(null=True, blank=True)
    is_canceled = models.BooleanField(default=False)

    class Meta:
        unique_together = ['event', 'original_start_dt']

    def __str__(self):
        action = "Canceled" if self.is_canceled else f"Moved to {self.new_start_dt}"
        return f"Exception for {self.event.title}: {action}"


class CalendarOverrideLog(models.Model):
    """
    Log when a user overrides a protected-event conflict.
    Part of the Habit Protection Layer.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_override_logs',
    )
    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name='override_logs_as_moved',
    )
    overridden_event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name='override_logs_as_overridden',
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Override: {self.event.title} over {self.overridden_event.title}"
