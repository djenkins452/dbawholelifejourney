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
    SOURCE_MEDICINE_SCHEDULE = 'medicine_schedule'
    SOURCE_FAITH_ROUTINE = 'faith_routine'
    SOURCE_WORKOUT_SCHEDULE = 'workout_schedule'

    SOURCE_TYPE_CHOICES = [
        (SOURCE_NONE, 'None (Manual)'),
        (SOURCE_TASK, 'Task'),
        (SOURCE_GOAL, 'Goal'),
        (SOURCE_GOAL_MILESTONE, 'Goal Milestone'),
        (SOURCE_HABIT, 'Habit'),
        (SOURCE_LIFE_EVENT, 'Life Event'),
        (SOURCE_EXTERNAL, 'External'),
        (SOURCE_MEDICINE_SCHEDULE, 'Medicine Schedule'),
        (SOURCE_FAITH_ROUTINE, 'Faith Routine'),
        (SOURCE_WORKOUT_SCHEDULE, 'Workout Schedule'),
    ]

    # Commitment levels (shared vocabulary with Task, HabitGoal)
    COMMITMENT_OPTIONAL = 'optional'
    COMMITMENT_IMPORTANT = 'important'
    COMMITMENT_NON_NEGOTIABLE = 'non_negotiable'

    COMMITMENT_LEVEL_CHOICES = [
        (COMMITMENT_OPTIONAL, 'Optional'),
        (COMMITMENT_IMPORTANT, 'Important'),
        (COMMITMENT_NON_NEGOTIABLE, 'Non-Negotiable'),
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

    commitment_level = models.CharField(
        max_length=20,
        choices=COMMITMENT_LEVEL_CHOICES,
        default=COMMITMENT_IMPORTANT,
        help_text='Importance classification. Non-negotiable commitments are '
                  'never compensable in the compensatory reasoning engine.',
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
        max_length=128,
        db_index=True,
        help_text='SHA-256 hash for deterministic duplicate prevention',
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Soft-delete timestamp. Set when status transitions to canceled.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_dt']
        indexes = [
            models.Index(fields=['user', 'start_dt']),
            models.Index(fields=['user', 'source_type', 'source_id']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'deleted_at']),
            models.Index(
                fields=['user', 'title', 'start_dt', 'end_dt'],
                name='idx_cal_event_semantic_dup',
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'idempotency_key'],
                condition=models.Q(deleted_at__isnull=True),
                name='uq_calendar_event_user_idempotency',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.idempotency_key:
            raise ValueError(
                "CalendarEvent.idempotency_key must be set before save(). "
                "Use compute_idempotency_key() from "
                "apps.calendar_engine.utils.idempotency."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_event_kind_display()}) - {self.start_dt:%Y-%m-%d}"

    def soft_delete(self):
        """Soft-delete by setting status to canceled and recording timestamp."""
        from apps.core.time.system_clock import get_current_time
        self.status = self.STATUS_CANCELED
        self.deleted_at = get_current_time()
        self.save(update_fields=['status', 'deleted_at', 'updated_at'])

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

        Uses the recurrence's timezone to preserve wall-clock time across
        DST boundaries.  E.g. "6 PM every Wednesday" stays 6 PM even when
        the UTC offset changes from -06:00 (CST) to -05:00 (CDT).
        """
        import datetime as dt
        from zoneinfo import ZoneInfo
        from django.utils import timezone as tz_utils

        occurrences = []
        event_duration = self.event.end_dt - self.event.start_dt

        # Work in the recurrence's local timezone so timedelta advances
        # preserve the wall-clock time across DST transitions.
        try:
            local_tz = ZoneInfo(self.timezone)
        except (KeyError, Exception):
            local_tz = tz_utils.get_current_timezone()

        local_start = self.event.start_dt.astimezone(local_tz)
        local_time = local_start.time()
        current_date = local_start.date()

        # Cap iterations for safety
        max_iterations = 1000
        iteration = 0
        generated = 0

        while iteration < max_iterations:
            iteration += 1

            # Build occurrence at the same wall-clock time on current_date
            naive_dt = dt.datetime.combine(current_date, local_time)
            try:
                current = tz_utils.make_aware(naive_dt, local_tz)
            except Exception:
                current = naive_dt.replace(tzinfo=local_tz)

            if current > range_end:
                break

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
                        current_date = self._advance_date(current_date)
                        continue

                occurrences.append((current, current + event_duration))
                generated += 1

            current_date = self._advance_date(current_date)

        return occurrences

    def _advance_date(self, current_date):
        """Advance a date by the recurrence interval. Used by get_occurrences."""
        import datetime as dt

        if self.frequency == self.FREQ_DAILY:
            return current_date + dt.timedelta(days=self.interval)
        elif self.frequency == self.FREQ_WEEKLY:
            if self.byweekday:
                next_date = current_date + dt.timedelta(days=1)
                days_checked = 0
                while days_checked < 7 * self.interval:
                    if next_date.isoweekday() in self.byweekday:
                        return next_date
                    next_date += dt.timedelta(days=1)
                    days_checked += 1
                return current_date + dt.timedelta(weeks=self.interval)
            return current_date + dt.timedelta(weeks=self.interval)
        elif self.frequency == self.FREQ_MONTHLY:
            month = current_date.month + self.interval
            year = current_date.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            day = min(current_date.day, 28)
            return current_date.replace(year=year, month=month, day=day)
        return current_date + dt.timedelta(days=1)

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


class DeclinedSuggestion(models.Model):
    """
    Tracks suggestions the user has declined so they don't reappear
    for the same item on the same date.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='declined_suggestions',
    )
    source_type = models.CharField(max_length=20)
    source_id = models.CharField(max_length=100)
    declined_date = models.DateField(
        help_text='The date the suggestion was declined for',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'source_type', 'source_id', 'declined_date']

    def __str__(self):
        return f"Declined {self.source_type}:{self.source_id} on {self.declined_date}"
