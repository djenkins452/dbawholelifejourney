"""Lightweight latency instrumentation for dashboard action endpoints.

Emits a single structured log line per instrumented action so we can
measure end-to-end server-side time before and after Phase 1 of the
dashboard-action latency project (kill double-fetch + defer Class A
health summary builder).

Log line format (matches the spec):

    [DASHBOARD_ACTION_TIMING] action=<name> user=<id> total_ms=<int>
        [short_circuit=<bool>] [path=<request_path>]

Usage:

    with action_timing("water_log", request):
        ...do the write + emit events...

The context manager is fail-safe: even if the inner block raises, the
timing log fires (with `error=1` appended) so we can still see how long
the failing request took.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("dashboard.action.timing")


@contextmanager
def action_timing(action: str, request=None, **extra):
    """Time an action and emit a structured `[DASHBOARD_ACTION_TIMING]`
    log line on exit.

    Args:
        action: short identifier — "water_log", "intake_group_log",
                "task_toggle", "routine_toggle", "block_complete", etc.
        request: optional Django HttpRequest for user_id + path context.
        **extra: extra k=v fields to append to the log line
                 (e.g. short_circuit=True, drink_type='coffee').

    Always emits, even if the inner block raises.
    """
    started = time.perf_counter()
    error = False
    try:
        yield
    except Exception:
        error = True
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        user_id = "anon"
        path = "?"
        if request is not None:
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                user_id = str(getattr(user, "pk", "?"))
            path = getattr(request, "path", "?")
        parts = [
            f"action={action}",
            f"user={user_id}",
            f"total_ms={elapsed_ms}",
            f"path={path}",
        ]
        for k, v in extra.items():
            parts.append(f"{k}={v}")
        if error:
            parts.append("error=1")
        logger.info("[DASHBOARD_ACTION_TIMING] " + " ".join(parts))
