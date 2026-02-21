"""
Engine Instrumentation — Decorators and helpers for diagnostics tracing.

Design principles:
- Failures in instrumentation NEVER break engine execution
- Zero changes to engine function signatures
- Minimal overhead (< 1ms per decorator invocation)
- All DB writes are fire-and-forget with try/except
- No-op when no trace context is active (e.g., in tests)

Project: Whole Life Journey
Path: apps/core/ai_observability/instrumentation.py
"""

import functools
import logging
import time

from django.utils import timezone

logger = logging.getLogger(__name__)


def log_engine_run(engine_name, phase):
    """
    Decorator that records an EngineRun for the wrapped function.

    Usage:
        @log_engine_run("UAL", 3)
        def run_arbitration(user):
            ...

    The decorator:
    1. Gets trace_id from contextvars (set by middleware or scheduler)
    2. Records started_at
    3. Calls the wrapped function
    4. Records ended_at, duration, status
    5. Writes EngineRun to DB (fire-and-forget)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from apps.core.ai_observability.trace import get_trace_id

            trace_id = get_trace_id()
            if not trace_id:
                return func(*args, **kwargs)

            started_at = timezone.now()
            start_mono = time.monotonic()
            status = "success"
            error_type = ""
            error_message = ""
            result = None

            # Extract user_id from first arg if it looks like a User
            user_id = None
            if args and hasattr(args[0], "id") and hasattr(args[0], "email"):
                user_id = args[0].id

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                error_message = str(e)[:500]
                raise
            finally:
                duration_ms = int((time.monotonic() - start_mono) * 1000)
                _write_engine_run(
                    trace_id=trace_id,
                    engine_name=engine_name,
                    phase=phase,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status=status,
                    error_type=error_type,
                    error_message=error_message,
                    user_id=user_id,
                )

        return wrapper

    return decorator


def log_engine_span(engine_name, span_name):
    """
    Decorator that records an EngineSpan for a sub-step within an engine.

    Usage:
        @log_engine_span("UAL", "collect_signals")
        def collect_signals(user):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from apps.core.ai_observability.trace import get_trace_id

            trace_id = get_trace_id()
            if not trace_id:
                return func(*args, **kwargs)

            started_at = timezone.now()
            start_mono = time.monotonic()
            status = "success"

            try:
                return func(*args, **kwargs)
            except Exception:
                status = "error"
                raise
            finally:
                duration_ms = int((time.monotonic() - start_mono) * 1000)
                _write_engine_span(
                    trace_id=trace_id,
                    engine_name=engine_name,
                    span_name=span_name,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status=status,
                )

        return wrapper

    return decorator


def record_decision(
    engine_name,
    decision_type,
    decision,
    rationale="",
    inputs_summary=None,
    affected_items=None,
    user_id=None,
    confidence=None,
):
    """
    Record a decision made by an engine (called explicitly, not a decorator).

    Usage:
        record_decision(
            engine_name="UAL",
            decision_type="arbitration",
            decision=f"SCENARIO={result.dominant_scenario}",
            rationale=f"Confidence {result.confidence:.2f}",
            inputs_summary={"strengths": result.raw_strengths},
            user_id=user.id,
            confidence=result.confidence,
        )
    """
    try:
        from apps.core.ai_observability.trace import get_trace_id

        trace_id = get_trace_id()
        if not trace_id:
            return

        from apps.core.ai_observability.models import DecisionRecord

        DecisionRecord.objects.create(
            trace_id=trace_id,
            engine_name=engine_name,
            decision_type=decision_type,
            decision=str(decision)[:200],
            rationale=str(rationale)[:1000] if rationale else "",
            inputs_summary=inputs_summary or {},
            affected_items=affected_items or [],
            user_id=user_id,
            confidence=confidence,
        )
    except Exception as e:
        logger.debug("Decision record write failed: %s", e)


# ---------------------------------------------------------------------------
# Internal fire-and-forget writers
# ---------------------------------------------------------------------------


def _write_engine_run(**kwargs):
    """Fire-and-forget EngineRun creation."""
    try:
        from datetime import timedelta

        from apps.core.ai_observability.models import EngineRun

        ended_at = kwargs["started_at"] + timedelta(milliseconds=kwargs["duration_ms"])
        EngineRun.objects.create(ended_at=ended_at, **kwargs)
    except Exception as e:
        logger.debug("EngineRun write failed: %s", e)


def _write_engine_span(**kwargs):
    """Fire-and-forget EngineSpan creation."""
    try:
        from datetime import timedelta

        from apps.core.ai_observability.models import EngineSpan

        ended_at = kwargs["started_at"] + timedelta(milliseconds=kwargs["duration_ms"])
        EngineSpan.objects.create(ended_at=ended_at, **kwargs)
    except Exception as e:
        logger.debug("EngineSpan write failed: %s", e)
