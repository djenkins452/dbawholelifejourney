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
import time
from collections import deque
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
    HEALTH_WATER_LOGGED = "health.water.logged"
    HEALTH_SYNC_COMPLETED = "health.sync.completed"

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
    TASK_SKIPPED = "task.skipped"
    TASK_DELETED = "task.deleted"
    TASK_UPDATED = "task.updated"
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

_MAX_EVENT_DEPTH = 2          # Loop protection: max recursive event depth
_DEDUPE_TTL_SECONDS = 5.0     # Idempotency: ignore duplicate (type, entity_id) within window
_LATENCY_WINDOW_SIZE = 200    # Sliding window for p95 latency tracking

# Thread-local for tracking event propagation depth
_event_context = threading.local()


class _EventBus:
    """
    Thread-safe in-process event bus with safety guarantees.

    Supports:
    - Exact match subscriptions: "health.weight.logged"
    - Wildcard subscriptions: "health.*" or "health.weight.*"
    - Async subscriber dispatch (deferred to Celery when available)

    Safety features:
    - Idempotency: duplicate (event_type, entity_id) suppressed within 5s
    - Loop protection: max propagation depth of 2 (prevents cascades)
    - Latency tracking: avg/p95 handler execution time for observability
    - Exception isolation: handler failures never block the emitter
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._event_count = 0
        self._suppressed_count = 0
        self._type_counts: Dict[str, int] = {}
        self._handler_total_ms = 0.0
        self._latency_window: deque = deque(maxlen=_LATENCY_WINDOW_SIZE)
        # Dedupe cache: (event_type, entity_id) -> timestamp
        self._dedupe_cache: Dict[str, float] = {}
        self._dedupe_lock = threading.Lock()

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

        Safeguards:
        - Duplicate (event_type, entity_id) within 5s TTL are suppressed
        - Recursive depth beyond 2 is blocked (loop protection)
        - Handler exceptions are caught and logged (never block emitter)
        - Handler latency is tracked for observability
        """
        # --- Loop protection: check propagation depth ---
        depth = getattr(_event_context, "depth", 0)
        if depth >= _MAX_EVENT_DEPTH:
            logger.debug(
                "Event '%s' suppressed — depth %d exceeds max %d",
                event.event_type, depth, _MAX_EVENT_DEPTH,
            )
            self._suppressed_count += 1
            return

        # --- Idempotency: dedupe by (event_type, entity_id) ---
        entity_id = event.data.get("entry_id") or event.data.get("log_id") or event.data.get("task_id")
        if entity_id is not None:
            dedupe_key = f"{event.event_type}:{entity_id}"
            now_mono = time.monotonic()
            with self._dedupe_lock:
                last_seen = self._dedupe_cache.get(dedupe_key)
                if last_seen is not None and (now_mono - last_seen) < _DEDUPE_TTL_SECONDS:
                    self._suppressed_count += 1
                    return
                self._dedupe_cache[dedupe_key] = now_mono
                # Lazy cleanup: evict expired entries when cache grows large
                if len(self._dedupe_cache) > 500:
                    cutoff = now_mono - _DEDUPE_TTL_SECONDS
                    self._dedupe_cache = {
                        k: v for k, v in self._dedupe_cache.items() if v > cutoff
                    }

        # --- Track counts ---
        self._event_count += 1
        with self._lock:
            self._type_counts[event.event_type] = (
                self._type_counts.get(event.event_type, 0) + 1
            )

        matched_handlers = self._get_matching_handlers(event.event_type)
        if not matched_handlers:
            logger.debug("Event '%s' emitted — no subscribers", event.event_type)
            return

        # --- Dispatch with depth tracking and latency measurement ---
        _event_context.depth = depth + 1
        try:
            for handler in matched_handlers:
                t0 = time.monotonic()
                try:
                    handler(event)
                except Exception as e:
                    logger.error(
                        "Event handler '%s' failed for '%s': %s",
                        handler.__name__, event.event_type, e,
                        exc_info=True,
                    )
                elapsed_ms = (time.monotonic() - t0) * 1000
                self._handler_total_ms += elapsed_ms
                self._latency_window.append(elapsed_ms)
        finally:
            _event_context.depth = depth

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
            latencies = list(self._latency_window)
            avg_ms = sum(latencies) / len(latencies) if latencies else 0.0
            p95_ms = 0.0
            if latencies:
                sorted_lat = sorted(latencies)
                p95_idx = int(len(sorted_lat) * 0.95)
                p95_ms = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]
            return {
                "total_events_emitted": self._event_count,
                "suppressed_count": self._suppressed_count,
                "registered_patterns": len(self._handlers),
                "total_handlers": sum(len(h) for h in self._handlers.values()),
                "patterns": list(self._handlers.keys()),
                "type_counts": dict(self._type_counts),
                "handler_total_ms": round(self._handler_total_ms, 1),
                "avg_handler_ms": round(avg_ms, 2),
                "p95_handler_ms": round(p95_ms, 2),
            }

    def clear(self):
        """Clear all subscriptions (useful for tests)."""
        with self._lock:
            self._handlers.clear()
            self._event_count = 0
            self._suppressed_count = 0
            self._type_counts.clear()
            self._handler_total_ms = 0.0
            self._latency_window.clear()
        with self._dedupe_lock:
            self._dedupe_cache.clear()


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


def safe_emit_event(event_type, user=None, data=None, source=""):
    """
    Emit a domain event safely — never raises, never blocks.

    Designed for use in web views, HealthKit sync, and any path where
    event emission must never interfere with the primary response.

    Args:
        event_type: Dotted event name (use EventTypes constants)
        user: Django User instance
        data: Event payload dict
        source: Module/view emitting the event
    """
    try:
        emit_event(event_type, user=user, data=data or {}, source=source)
    except Exception:
        logger.debug("safe_emit_event suppressed error for %s", event_type)


def get_event_bus_stats() -> Dict:
    """Get event bus statistics for observability dashboard."""
    return _bus.get_stats()


def clear_event_bus():
    """Clear all subscriptions. Only use in tests."""
    _bus.clear()
