"""
Trace Context — Request-level correlation for intelligence engines.

Uses contextvars to propagate a trace_id through the call stack
without modifying any engine function signatures.

Every user request (via middleware) and every scheduled task run
(via scheduler_runner) creates a new trace_id that flows through:
SUE -> UAIO -> SAE -> PIE -> PRIE -> UAL -> PGE/DBE/WIRE -> DNE

Project: Whole Life Journey
Path: apps/core/ai_observability/trace.py
"""

import uuid
import logging
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
_trace_source_var: ContextVar[str] = ContextVar("trace_source", default="")


def generate_trace_id() -> str:
    """Generate a UUID4 trace ID."""
    return str(uuid.uuid4())


def get_trace_id() -> str:
    """Get the current trace_id from context. Returns '' if none."""
    return _trace_id_var.get()


def get_trace_source() -> str:
    """Get the trace source (e.g., 'request', 'scheduler', 'intelligence_hook')."""
    return _trace_source_var.get()


@contextmanager
def trace_context(trace_id=None, source="unknown"):
    """
    Context manager to set trace_id for the duration of a block.

    Usage:
        with trace_context(source='request') as tid:
            run_arbitration(user)  # decorators pick up tid automatically

    Args:
        trace_id: Optional explicit trace_id. Auto-generated if None.
        source: Label for what initiated this trace.

    Yields:
        The trace_id string.
    """
    tid = trace_id or generate_trace_id()
    token_id = _trace_id_var.set(tid)
    token_src = _trace_source_var.set(source)
    try:
        yield tid
    finally:
        _trace_id_var.reset(token_id)
        _trace_source_var.reset(token_src)
