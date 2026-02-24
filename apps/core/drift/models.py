"""
Phase 10 — Schedule Drift Detection Models.

ExecutionLog: The sole behavioral log table — tracks schedule changes
    with instability weighting.
DriftSignal: Records when schedule instability crosses escalation threshold.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExecutionLog(models.Model):
    """
    The sole behavioral log table for schedule change events.

    Each entry records a calendar event modification (time shift, reschedule)
    with deterministic weight and instability points computed from the delta.
    """

    EVENT_TYPE_TIME_SHIFT = 'time_shift'
    EVENT_TYPE_DATE_CHANGE = 'date_change'
    EVENT_TYPE_CANCELED = 'canceled'

    EVENT_TYPE_CHOICES = [
        (EVENT_TYPE_TIME_SHIFT, 'Time Shift'),
        (EVENT_TYPE_DATE_CHANGE, 'Date Change'),
        (EVENT_TYPE_CANCELED, 'Canceled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='execution_logs',
    )
    calendar_event = models.ForeignKey(
        'calendar_engine.CalendarEvent',
        on_delete=models.CASCADE,
        related_name='cal_execution_logs',
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    instability_points = models.IntegerField(default=0)
    weight = models.IntegerField(default=0)
    idempotency_key = models.CharField(
        max_length=128,
        help_text='Deterministic key for log deduplication',
    )
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'core'
        db_table = 'core_execution_log'
        ordering = ['-occurred_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'idempotency_key'],
                name='uq_exec_log_user_idempotency',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'occurred_at']),
        ]

    def __str__(self):
        return (
            f"ExecutionLog user={self.user_id} "
            f"event={self.calendar_event_id} "
            f"pts={self.instability_points} w={self.weight}"
        )


class DriftSignal(models.Model):
    """
    Record of a schedule instability escalation signal.

    Created when rolling 7-day instability crosses threshold with
    Tier-1 or protected-time involvement. Unique per user/signal_type/window
    to prevent duplicate escalation within the same window.
    """

    SIGNAL_SCHEDULE_INSTABILITY = 'schedule_instability'

    SIGNAL_TYPE_CHOICES = [
        (SIGNAL_SCHEDULE_INSTABILITY, 'Schedule Instability'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='drift_signals',
    )
    signal_type = models.CharField(max_length=30, choices=SIGNAL_TYPE_CHOICES)
    window_start = models.DateField()
    window_end = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'core'
        db_table = 'core_drift_signal'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'signal_type', 'window_start'],
                name='uq_drift_signal_user_type_window',
            ),
        ]

    def __str__(self):
        return (
            f"DriftSignal user={self.user_id} "
            f"{self.signal_type} {self.window_start}–{self.window_end}"
        )
