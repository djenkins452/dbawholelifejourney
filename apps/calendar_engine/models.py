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

    # Commitment levels (shared vocabulary with Task, HabitGoal, RoutineSchedule)
    COMMITMENT_FOUNDATIONAL = 'foundational'
    COMMITMENT_IMPORTANT = 'important'
    COMMITMENT_FLEXIBLE = 'flexible'
    # Legacy aliases for backward compat during transition
    COMMITMENT_OPTIONAL = 'flexible'
    COMMITMENT_NON_NEGOTIABLE = 'foundational'

    COMMITMENT_LEVEL_CHOICES = [
        (COMMITMENT_FOUNDATIONAL, 'Foundational'),
        (COMMITMENT_IMPORTANT, 'Important'),
        (COMMITMENT_FLEXIBLE, 'Flexible'),
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

        Applies this event's RecurrenceException rows (moved/canceled single
        occurrences) — before 2026-07-07 they were silently ignored here.
        """
        event_duration = self.event.end_dt - self.event.start_dt
        return self.expand(
            self.event.start_dt, event_duration,
            frequency=self.frequency, byweekday=self.byweekday,
            interval=self.interval, until_dt=self.until_dt, count=self.count,
            tz_name=self.timezone, range_start=range_start, range_end=range_end,
            exceptions=self.event.recurrence_exceptions.all(),
        )

    @staticmethod
    def expand(anchor_start, duration, *, frequency, byweekday=None, interval=1,
               until_dt=None, count=None, tz_name='America/Chicago',
               range_start, range_end, exceptions=None, max_iterations=1000):
        """Calendar-native recurrence expansion — the one place recurrence +
        per-occurrence exceptions compose. DST-safe (iterates in the series'
        local timezone so wall-clock time is preserved across CST↔CDT), and
        applies exceptions (canceled occurrences dropped, moved ones relocated).

        Reused by AvailabilityBlock so calendar-native recurring objects share
        one engine. Task recurrence stays in life.RecurrencePattern.

        `exceptions` items expose .original_start_dt / .is_canceled /
        .new_start_dt / .new_end_dt (a small duck-typed object).
        """
        import datetime as _dt
        from zoneinfo import ZoneInfo
        from django.utils import timezone as _tz

        interval = max(int(interval or 1), 1)
        byweekday = list(byweekday or [])

        # Index exceptions by their original occurrence instant (UTC).
        exc_map = {}
        for exc in (exceptions or []):
            try:
                exc_map[exc.original_start_dt.astimezone(_dt.timezone.utc)] = exc
            except Exception:
                continue

        try:
            local_tz = ZoneInfo(tz_name)
        except Exception:
            local_tz = _tz.get_current_timezone()

        local_start = anchor_start.astimezone(local_tz)
        local_time = local_start.time()
        current_date = local_start.date()

        def _advance(d):
            if frequency == RecurrenceRule.FREQ_DAILY:
                return d + _dt.timedelta(days=interval)
            if frequency == RecurrenceRule.FREQ_WEEKLY:
                if byweekday:
                    nxt = d + _dt.timedelta(days=1)
                    checked = 0
                    while checked < 7 * interval:
                        if nxt.isoweekday() in byweekday:
                            return nxt
                        nxt += _dt.timedelta(days=1)
                        checked += 1
                    return d + _dt.timedelta(weeks=interval)
                return d + _dt.timedelta(weeks=interval)
            if frequency == RecurrenceRule.FREQ_MONTHLY:
                month = d.month + interval
                year = d.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                return d.replace(year=year, month=month, day=min(d.day, 28))
            return d + _dt.timedelta(days=1)

        occurrences = []
        iteration = generated = 0
        while iteration < max_iterations:
            iteration += 1
            naive = _dt.datetime.combine(current_date, local_time)
            try:
                current = _tz.make_aware(naive, local_tz)
            except Exception:
                current = naive.replace(tzinfo=local_tz)

            if current > range_end:
                break
            if count is not None and generated >= count:
                break
            if until_dt is not None and current > until_dt:
                break
            if byweekday and current.isoweekday() not in byweekday:
                current_date = _advance(current_date)
                continue

            generated += 1
            exc = exc_map.get(current.astimezone(_dt.timezone.utc))
            if exc is not None:
                if getattr(exc, 'is_canceled', False):
                    current_date = _advance(current_date)
                    continue
                new_start = getattr(exc, 'new_start_dt', None)
                if new_start is not None:
                    new_end = getattr(exc, 'new_end_dt', None) or (new_start + duration)
                    if range_start <= new_start <= range_end:
                        occurrences.append((new_start, new_end))
                    current_date = _advance(current_date)
                    continue

            if current >= range_start:
                occurrences.append((current, current + duration))
            current_date = _advance(current_date)

        return occurrences


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


class AvailabilityBlock(models.Model):
    """A calendar-native planning constraint — when the user is (un)available.

    Availability is inherently time-shaped, so the Calendar legitimately OWNS it
    (unlike Tasks/Medicine/Workouts, which the calendar only projects). An
    AvailabilityBlock is NOT a Task, Event, or Routine: it answers "when is the
    user realistically available?" so any planner can reason about free time.

    Recurrence reuses RecurrenceRule.expand() (the one calendar-native engine).
    Task recurrence stays in life.RecurrencePattern and is not merged here.
    Per-occurrence edits (this/future/series) are supported Outlook-style:
    single-occurrence moves/cancels live in the JSON ``exceptions`` list (planning
    constraints aren't reported on independently, so no separate table); "this and
    future" splits the series into a new block.
    """

    KIND_AVAILABLE = 'available'
    KIND_UNAVAILABLE = 'unavailable'
    KIND_CHOICES = [
        (KIND_AVAILABLE, 'Available'),
        (KIND_UNAVAILABLE, 'Unavailable'),
    ]

    # Recurrence frequency ('' = one-off). Mirrors RecurrenceRule vocabulary.
    FREQ_NONE = ''
    FREQ_DAILY = 'daily'
    FREQ_WEEKLY = 'weekly'
    FREQ_MONTHLY = 'monthly'
    FREQUENCY_CHOICES = [
        (FREQ_NONE, 'Does not repeat'),
        (FREQ_DAILY, 'Daily'),
        (FREQ_WEEKLY, 'Weekly'),
        (FREQ_MONTHLY, 'Monthly'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='availability_blocks',
    )
    label = models.CharField(max_length=200, default='Work')
    kind = models.CharField(
        max_length=12, choices=KIND_CHOICES, default=KIND_UNAVAILABLE,
        help_text='Whether this block marks time as available or unavailable.',
    )

    # Anchor occurrence (aware). Recurrence expands from this wall-clock time.
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()

    # Recurrence (inline — calendar-native engine). Empty frequency = one-off.
    frequency = models.CharField(
        max_length=10, choices=FREQUENCY_CHOICES, default=FREQ_NONE, blank=True,
    )
    byweekday = models.JSONField(
        default=list, blank=True,
        help_text='ISO weekday numbers (1=Mon..7=Sun) for weekly recurrence.',
    )
    interval = models.PositiveIntegerField(default=1)
    until_dt = models.DateTimeField(null=True, blank=True)
    count = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='America/Chicago')

    # Single-occurrence overrides (this occurrence moved/canceled). Kept as JSON
    # because availability exceptions only alter recurrence generation (PTO, a
    # doctor appt) — they aren't reported on independently. Each item:
    #   {"original_start_dt": ISO, "new_start_dt": ISO|null,
    #    "new_end_dt": ISO|null, "is_canceled": bool}
    exceptions = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_dt']
        indexes = [
            models.Index(fields=['user', 'start_dt']),
            models.Index(fields=['user', 'is_active', 'deleted_at']),
        ]

    def __str__(self):
        return f"{self.label} ({self.get_kind_display()}) {self.start_dt:%Y-%m-%d %H:%M}"

    # ---- read ----

    @classmethod
    def active(cls, user):
        """Canonical accessor: active, non-deleted blocks for a user."""
        return cls.objects.filter(user=user, is_active=True, deleted_at__isnull=True)

    @property
    def is_recurring(self):
        return bool(self.frequency)

    @property
    def duration(self):
        return self.end_dt - self.start_dt

    class _Exc:
        """Duck-typed adapter so JSON exception dicts work with RecurrenceRule.expand."""
        def __init__(self, d):
            from django.utils.dateparse import parse_datetime
            self.original_start_dt = parse_datetime(d.get('original_start_dt'))
            self.new_start_dt = parse_datetime(d['new_start_dt']) if d.get('new_start_dt') else None
            self.new_end_dt = parse_datetime(d['new_end_dt']) if d.get('new_end_dt') else None
            self.is_canceled = bool(d.get('is_canceled'))

    def get_occurrences(self, range_start, range_end):
        """Return (start, end) tuples within the range. One-off blocks return their
        single interval; recurring blocks use RecurrenceRule.expand (DST-safe,
        exception-aware) with the JSON exceptions applied."""
        if not self.is_recurring:
            if self.start_dt < range_end and self.end_dt > range_start:
                return [(self.start_dt, self.end_dt)]
            return []
        excs = [self._Exc(d) for d in (self.exceptions or []) if d.get('original_start_dt')]
        return RecurrenceRule.expand(
            self.start_dt, self.duration,
            frequency=self.frequency, byweekday=self.byweekday,
            interval=self.interval, until_dt=self.until_dt, count=self.count,
            tz_name=self.timezone, range_start=range_start, range_end=range_end,
            exceptions=excs,
        )

    # ---- write (Outlook-style recurring edits) ----

    def soft_delete(self):
        from apps.core.time.system_clock import get_current_time
        self.is_active = False
        self.deleted_at = get_current_time()
        self.save(update_fields=['is_active', 'deleted_at', 'updated_at'])

    def _upsert_exception(self, original_start_dt, *, new_start_dt=None,
                          new_end_dt=None, is_canceled=False):
        key = original_start_dt.isoformat()
        entry = {
            'original_start_dt': key,
            'new_start_dt': new_start_dt.isoformat() if new_start_dt else None,
            'new_end_dt': new_end_dt.isoformat() if new_end_dt else None,
            'is_canceled': is_canceled,
        }
        rest = [e for e in (self.exceptions or []) if e.get('original_start_dt') != key]
        self.exceptions = rest + [entry]
        self.save(update_fields=['exceptions', 'updated_at'])

    def cancel_occurrence(self, original_start_dt):
        """Delete a single occurrence (this occurrence only)."""
        self._upsert_exception(original_start_dt, is_canceled=True)

    def move_occurrence(self, original_start_dt, new_start_dt, new_end_dt=None):
        """Move a single occurrence (this occurrence only)."""
        self._upsert_exception(original_start_dt, new_start_dt=new_start_dt,
                               new_end_dt=new_end_dt)

    def split_future(self, boundary_start, **fields):
        """"This and future": cap this series just before *boundary_start* and
        create a new block from the boundary forward with *fields* applied.
        Returns the new block."""
        import datetime as _dt
        editable = ('label', 'kind', 'start_dt', 'end_dt', 'frequency',
                    'byweekday', 'interval', 'until_dt', 'count', 'timezone')
        self.until_dt = boundary_start - _dt.timedelta(seconds=1)
        self.save(update_fields=['until_dt', 'updated_at'])

        seed = {f: getattr(self, f) for f in editable}
        seed['start_dt'] = boundary_start
        seed['until_dt'] = None
        for k, v in fields.items():
            if k in editable:
                seed[k] = v
        if 'end_dt' not in fields:
            seed['end_dt'] = seed['start_dt'] + (self.end_dt - self.start_dt)
        return AvailabilityBlock.objects.create(user=self.user, **seed)
