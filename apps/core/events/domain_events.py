"""
Domain Events — Lightweight event bus for closing the intelligence trigger gap.

Project: Whole Life Journey
Path: apps/core/events/domain_events.py
Purpose: Enables domain modules (health, journal, faith, etc.) to emit events
         that the intelligence pipeline can react to, without coupling domains
         to specific engines.

Problem solved:
    Currently, intelligence triggers (PIE insights, PRIE predictions) only fire
    on scheduled intervals. Domain mutations happen in real-time but don't notify
    the intelligence layer. This event bus closes that gap.

Usage — Emitting events:
    from apps.core.events.domain_events import emit_event

    # After saving a weight log:
    emit_event("health.weight.logged", user=request.user, data={
        "weight": 185.5, "unit": "lbs", "source": "manual"
    })

    # After completing a journal entry:
    emit_event("journal.entry.created", user=request.user, data={
        "entry_id": entry.id, "mood": "good", "word_count": 250
    })

Usage — Subscribing to events:
    from apps.core.events.domain_events import subscribe

    @subscribe("health.weight.logged")
    def on_weight_logged(event):
        # Trigger PIE insight check for weight patterns
        check_weight_pattern(event.user, event.data)

    @subscribe("health.*")
    def on_any_health_event(event):
        # Invalidate SAE cache when any health data changes
        invalidate_user_state_cache(event.user)

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import fnmatch
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from functools import wraps

from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# Event Definition
# =========================================================================

@dataclass
class DomainEvent:
    """A domain event emitted when something meaningful happens in the system."""
    event_type: str                    # Dotted name: "health.weight.logged"
    user: Any = None                   # Django User instance
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=timezone.now)
    source: str = ""                   # Module that emitted the event
    trace_id: str = ""                 # For correlation with engine telemetry

    @property
    def domain(self) -> str:
        """Extract domain from event type (first segment)."""
        return self.event_type.split(".")[0] if "." in self.event_type else self.event_type


# =========================================================================
# Standard Event Types
# =========================================================================

class EventTypes:
    """Standard event type constants to prevent typos."""

    # Health domain
    HEALTH_WEIGHT_LOGGED = "health.weight.logged"
    HEALTH_BP_LOGGED = "health.bp.logged"
    HEALTH_GLUCOSE_LOGGED = "health.glucose.logged"
    HEALTH_MEDICATION_TAKEN = "health.medication.taken"
    HEALTH_MEDICATION_MISSED = "health.medication.missed"
    HEALTH_WORKOUT_COMPLETED = "health.workout.completed"
    HEALTH_NUTRITION_LOGGED = "health.nutrition.logged"
    HEALTH_FASTING_STARTED = "health.fasting.started"
    HEALTH_FASTING_ENDED = "health.fasting.ended"
    HEALTH_SLEEP_LOGGED = "health.sleep.logged"

    # Journal domain
    JOURNAL_ENTRY_CREATED = "journal.entry.created"
    JOURNAL_MOOD_LOGGED = "journal.mood.logged"

    # Faith domain
    FAITH_PRAYER_CREATED = "faith.prayer.created"
    FAITH_PRAYER_ANSWERED = "faith.prayer.answered"
    FAITH_SCRIPTURE_READ = "faith.scripture.read"
    FAITH_READING_COMPLETED = "faith.reading.completed"

    # Purpose domain
    PURPOSE_GOAL_CREATED = "purpose.goal.created"
    PURPOSE_GOAL_COMPLETED = "purpose.goal.completed"
    PURPOSE_HABIT_LOGGED = "purpose.habit.logged"
    PURPOSE_HABIT_STREAK_BROKEN = "purpose.habit.streak_broken"

    # Tasks domain
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    TASK_OVERDUE = "task.overdue"

    # CoS domain
    COS_ACTION_EXECUTED = "cos.action.executed"
    COS_ACTION_FAILED = "cos.action.failed"
    COS_CONVERSATION_STARTED = "cos.conversation.started"
    COS_BRIEFING_DELIVERED = "cos.briefing.delivered"

    # Finance domain
    FINANCE_TRANSACTION_LOGGED = "finance.transaction.logged"
    FINANCE_BUDGET_ALERT = "finance.budget.alert"

    # System domain
    SYSTEM_ENGINE_COMPLETED = "system.engine.completed"
    SYSTEM_ENGINE_FAILED = "system.engine.failed"
    SYSTEM_CACHE_INVALIDATED = "system.cache.invalidated"


# =========================================================================
# Event Bus Implementation
# =========================================================================

class _EventBus:
    """
    Thread-safe in-process event bus.

    Supports:
    - Exact match subscriptions: "health.weight.logged"
    - Wildcard subscriptions: "health.*" or "health.weight.*"
    - Synchronous dispatch (handlers run in the emitting thread)

    Design decisions:
    - Synchronous by default for simplicity and debuggability
    - Handlers that raise exceptions are caught and logged (never block emitter)
    - Thread-safe for concurrent access from Celery workers
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._event_count = 0

    def subscribe(self, event_pattern: str, handler: Callable):
        """
        Subscribe a handler to an event pattern.

        Args:
            event_pattern: Exact event type or wildcard pattern (e.g., "health.*")
            handler: Callable that accepts a DomainEvent
        """
        with self._lock:
            if event_pattern not in self._handlers:
                self._handlers[event_pattern] = []
            self._handlers[event_pattern].append(handler)
            logger.debug(
                "Event bus: subscribed %s to '%s'",
                handler.__name__, event_pattern
            )

    def emit(self, event: DomainEvent):
        """
        Emit an event to all matching subscribers.

        Handlers that raise exceptions are caught and logged.
        The emitting code is never blocked by handler failures.
        """
        self._event_count += 1
        matched_handlers = self._get_matching_handlers(event.event_type)

        if not matched_handlers:
            logger.debug("Event '%s' emitted — no subscribers", event.event_type)
            return

        for handler in matched_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    "Event handler '%s' failed for '%s': %s",
                    handler.__name__, event.event_type, e,
                    exc_info=True,
                )

    def _get_matching_handlers(self, event_type: str) -> List[Callable]:
        """Find all handlers that match the event type (exact or wildcard)."""
        handlers = []
        with self._lock:
            for pattern, pattern_handlers in self._handlers.items():
                if pattern == event_type or fnmatch.fnmatch(event_type, pattern):
                    handlers.extend(pattern_handlers)
        return handlers

    def get_stats(self) -> Dict:
        """Get event bus statistics for observability."""
        with self._lock:
            return {
                "total_events_emitted": self._event_count,
                "registered_patterns": len(self._handlers),
                "total_handlers": sum(len(h) for h in self._handlers.values()),
                "patterns": list(self._handlers.keys()),
            }

    def clear(self):
        """Clear all subscriptions (useful for tests)."""
        with self._lock:
            self._handlers.clear()
            self._event_count = 0


# Singleton event bus
_bus = _EventBus()


# =========================================================================
# Public API
# =========================================================================

def emit_event(
    event_type: str,
    user=None,
    data: Optional[Dict] = None,
    source: str = "",
    trace_id: str = "",
):
    """
    Emit a domain event.

    This is the primary function domain modules should call when
    something meaningful happens.

    Args:
        event_type: Dotted event name (e.g., "health.weight.logged")
        user: Django User instance (optional)
        data: Event payload dict (optional)
        source: Module name emitting the event
        trace_id: Correlation ID for engine telemetry

    Example:
        emit_event("health.weight.logged", user=request.user, data={"weight": 185.5})
    """
    event = DomainEvent(
        event_type=event_type,
        user=user,
        data=data or {},
        source=source,
        trace_id=trace_id,
    )
    _bus.emit(event)


def subscribe(event_pattern: str):
    """
    Decorator to subscribe a function to an event pattern.

    Usage:
        @subscribe("health.weight.logged")
        def on_weight_logged(event):
            process_weight(event.user, event.data)

        @subscribe("health.*")
        def on_any_health_event(event):
            invalidate_cache(event.user)
    """
    def decorator(fn: Callable) -> Callable:
        _bus.subscribe(event_pattern, fn)
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def subscribe_handler(event_pattern: str, handler: Callable):
    """Non-decorator form of subscribe, for programmatic registration."""
    _bus.subscribe(event_pattern, handler)


def get_event_bus_stats() -> Dict:
    """Get event bus statistics for observability dashboard."""
    return _bus.get_stats()


def clear_event_bus():
    """Clear all subscriptions. Only use in tests."""
    _bus.clear()
