"""
Phase 10 — Schedule Drift Engine.

Detects weighted schedule instability over a rolling 7-day window.
Escalates only when Tier-1 or protected-time events are affected.
Logs a deterministic DriftSignal; prevents duplicate escalation.
"""

import hashlib
import logging

from django.db.models import Sum
from django.utils import timezone

from apps.core.drift.models import DriftSignal, ExecutionLog
from apps.core.drift.weights import compute_schedule_change_weight

logger = logging.getLogger(__name__)


class DriftEngine:
    """Schedule instability detection and controlled escalation."""

    INSTABILITY_THRESHOLD = 8
    MIN_CONTRIBUTING_EVENTS = 2

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @classmethod
    def record_schedule_change(cls, user, calendar_event, old_start, new_start):
        """
        Record a schedule change and evaluate instability.

        Called inside an outer atomic block after a CalendarEvent time
        change is persisted. PostgreSQL-safe — uses get_or_create to
        avoid IntegrityError aborting the outer transaction.

        Args:
            user: User instance.
            calendar_event: CalendarEvent that was moved.
            old_start: datetime — original start (aware).
            new_start: datetime — new start (aware).

        Returns:
            ExecutionLog or None (if idempotency dedupe).
        """
        result = compute_schedule_change_weight(old_start, new_start)

        # Deterministic idempotency key
        idem_key = cls._build_idempotency_key(
            user.id, calendar_event.id, old_start, new_start,
        )

        event_type = (
            ExecutionLog.EVENT_TYPE_DATE_CHANGE
            if result['date_changed']
            else ExecutionLog.EVENT_TYPE_TIME_SHIFT
        )

        log, created = ExecutionLog.objects.get_or_create(
            user=user,
            idempotency_key=idem_key,
            defaults={
                'calendar_event': calendar_event,
                'event_type': event_type,
                'instability_points': result['instability_points'],
                'weight': result['weight'],
                'meta': {
                    'delta_minutes': result['delta_minutes'],
                    'date_changed': result['date_changed'],
                    'old_start': old_start.isoformat(),
                    'new_start': new_start.isoformat(),
                },
            },
        )

        if not created:
            logger.debug(
                "Duplicate schedule change log for user=%s event=%s",
                user.id, calendar_event.id,
            )
            return None

        if result['instability_points'] > 0:
            cls.evaluate_schedule_instability(user)

        return log

    @classmethod
    def evaluate_schedule_instability(cls, user):
        """
        Evaluate rolling 7-day schedule instability for a user.

        If threshold is met with high-priority involvement and at least
        2 separate events contributed, creates a DriftSignal.

        Returns:
            DriftSignal or None.
        """
        now = timezone.now()
        window_end = now.date()
        window_start = window_end - timezone.timedelta(days=7)

        # 1) Query last 7 days with instability_points > 0
        logs = ExecutionLog.objects.filter(
            user=user,
            occurred_at__date__gte=window_start,
            occurred_at__date__lte=window_end,
            instability_points__gt=0,
        )

        agg = logs.aggregate(total=Sum('instability_points'))
        total_points = agg['total'] or 0

        # Update UserState score
        cls._update_user_state(user, total_points, now)

        if total_points < cls.INSTABILITY_THRESHOLD:
            return None

        # 2) Check distinct contributing events
        distinct_events = logs.values('calendar_event_id').distinct().count()
        if distinct_events < cls.MIN_CONTRIBUTING_EVENTS:
            return None

        # 3) Check high-priority involvement
        high_priority = cls._has_high_priority_involvement(user, logs)
        if not high_priority:
            return None

        # 4) Create DriftSignal (get_or_create prevents duplicates safely)
        return cls._create_signal(user, window_start, window_end, total_points, logs)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_idempotency_key(user_id, event_id, old_start, new_start):
        """Deterministic SHA-256 from change parameters."""
        raw = f"{user_id}:{event_id}:{old_start.isoformat()}:{new_start.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _update_user_state(user, total_points, now):
        """Update UserState.schedule_instability_score."""
        from apps.core.ai_state.models import UserState

        state, _ = UserState.objects.get_or_create(user=user)
        state.schedule_instability_score = total_points
        state.schedule_instability_last_updated = now
        state.save(update_fields=[
            'schedule_instability_score',
            'schedule_instability_last_updated',
        ])

    @staticmethod
    def _has_high_priority_involvement(user, logs):
        """
        Check if any affected CalendarEvent is:
        - is_protected=True, OR
        - linked to a Tier-1 ScheduledBlock, OR
        - linked to a high-priority Task (priority='now')
        """
        from apps.calendar_engine.models import CalendarEvent

        event_ids = list(logs.values_list('calendar_event_id', flat=True).distinct())
        events = CalendarEvent.objects.filter(pk__in=event_ids)

        for event in events:
            # Protected time
            if event.is_protected:
                return True

            # Check Tier-1 via blueprint
            try:
                blueprint = user.operating_blueprint
                if event.source_type == CalendarEvent.SOURCE_HABIT:
                    # Habit source — check if behavior is Tier-1
                    tier = blueprint.get_tier_for_behavior(event.source_id)
                    if tier == 1:
                        return True
            except Exception:
                pass

            # Check high-priority Task linkage
            if event.source_type == CalendarEvent.SOURCE_TASK and event.source_id:
                try:
                    from apps.life.models import Task
                    task = Task.objects.get(pk=int(event.source_id), user=user)
                    if task.priority == 'now':
                        return True
                except Exception:
                    pass

        return False

    @classmethod
    def _create_signal(cls, user, window_start, window_end, total_points, logs):
        """Create DriftSignal using get_or_create for PostgreSQL safety."""
        signal, created = DriftSignal.objects.get_or_create(
            user=user,
            signal_type=DriftSignal.SIGNAL_SCHEDULE_INSTABILITY,
            window_start=window_start,
            defaults={
                'window_end': window_end,
                'meta': {
                    'total_instability_points': total_points,
                    'contributing_event_count': (
                        logs.values('calendar_event_id').distinct().count()
                    ),
                },
            },
        )

        if created:
            logger.info(
                "DriftSignal created: user=%s points=%d window=%s–%s",
                user.id, total_points, window_start, window_end,
            )
            return signal

        logger.debug(
            "Duplicate DriftSignal for user=%s window=%s",
            user.id, window_start,
        )
        return None
