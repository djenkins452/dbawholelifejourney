"""
Deterministic Day Agenda Renderer — Pure Truth, Time-Bucketed

Thin rendering layer over the Today Engine. Does NOT compute time
buckets, merge data, or apply any logic. Just formats.

The Today Engine (apps/core/today/today_engine.py) is the single
source of truth for what today looks like.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Re-export for backward compat with tests
from apps.core.today.today_engine import (  # noqa: F401
    COMING_UP_WINDOW_MINUTES,
    _collect_routine_items,
    _sort_by_time,
)

# Banned words — output must never contain these
_BANNED_WORDS = frozenset({"items", "tasks", "routines"})

_SAFE_FALLBACK = (
    "Today\n\n"
    "Foundation:\n• None\n\n"
    "Overdue now:\n• None\n\n"
    "Coming up next:\n• None\n\n"
    "Later today:\n• None\n\n"
    "Completed:\n• None\n\n"
    "Next: Start with your next planned item."
)


def render_day_agenda(user) -> str:
    """Render a deterministic day agenda from the Today Engine.

    This output is FINAL — it is NOT passed to an LLM for rephrasing.
    """
    try:
        from apps.core.today.today_engine import get_today_context

        ctx = get_today_context(user)
        return _format_day_output(ctx)
    except Exception:
        logger.error(
            "[DAY RENDERER] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK


def _format_day_output(ctx: dict) -> str:
    """Format Today Engine context into the day agenda output."""

    def _fmt(bucket):
        if not bucket:
            return "• None"
        return "\n".join(f"• {entry['label']}" for entry in bucket)

    # The renderer owns the "Next:" label; strip a redundant leading "Next: "
    # from the canonical directive so we never emit "Next: Next: …"
    # (trust bug 2026-06-15).
    _nx = ctx.get('next', '') or ''
    _next_line = f"Next: {_nx[6:]}" if _nx.startswith("Next: ") else f"Next: {_nx}"

    lines = [
        "Today",
        "",
        "Foundation:",
        _fmt(ctx["foundation"]),
        "",
        "Overdue now:",
        _fmt(ctx["overdue"]),
        "",
        "Coming up next:",
        _fmt(ctx["coming_up"]),
        "",
        "Later today:",
        _fmt(ctx["later"]),
        "",
        "Completed:",
        _fmt(ctx["completed"]),
        "",
        _next_line,
    ]

    output = "\n".join(lines)
    _validate_output(output)
    return output


def _validate_output(output: str):
    """Validate that output contains no aggregation language."""
    output_lower = output.lower()
    for word in _BANNED_WORDS:
        if word in output_lower:
            logger.warning(
                "[DAY RENDERER] VALIDATION: banned word '%s' found in output",
                word,
            )
