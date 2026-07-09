# ==============================================================================
# File: apps/ai/model_interface/context_warm.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context source — a thin reader over StandingContextService
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Current Context source for the model interface (Pillar 4 deterministic policy).

HARDENING (Slice 7.2 — Blocker 3): this used to call `interpret()` (~850ms) and run its
OWN warm pipeline + cache — duplicating the executive picture that `StandingContextService`
already computes and that the EXISTING prod keep-alive worker already warms. That violated
"reuse before rebuilding." It is now a THIN, cache-first READER over
`StandingContextService`: it extracts the deterministic priority / critical-safety policy
that service already projects. No second heavy compute, no second warm task, no second cache.

Request-path-safe: `get_standing_context(..., allow_build=False)` is cache-first and
returns a pending shell on a cold miss → we return `(None, None)` → the Current Context
baseline reports `pending` honestly (the existing worker re-warms the shared cache).

Day-continuity is intentionally NOT sourced here (it is not in the standing context);
cross-turn continuity now comes from the conversation history wired into the runtime.
"""

import logging
from types import SimpleNamespace

from apps.ai.cos_services.serialization import cap as _cap
from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

_MAX_CRITICAL = 5


def read(user, *, allow_build=False):
    """Cache-first. Return (signals, continuity) for get_current_context_baseline, or
    (None, None) when the standing context is not yet warm. Never raises, never
    live-computes on the request path (allow_build stays False on the request path)."""
    try:
        from apps.ai.cos_services.standing_context import get_standing_context
        ctx = get_standing_context(user, allow_build=allow_build)
    except Exception:  # pragma: no cover - defensive
        logger.warning("mi.context: standing context read failed user=%s",
                       getattr(user, "id", "?"), exc_info=True)
        return None, None

    if not ctx or ctx.get("status") != "ready":
        return None, None

    exec_read = (ctx.get("executive_read") or "").strip()
    recommended = (ctx.get("recommended_focus") or "").strip()
    critical = ctx.get("critical_signals") or []

    priority_action = None
    if exec_read or recommended:
        priority_action = {
            "text": exec_read or recommended,
            "recommended_focus": recommended,
            "source": "standing_context",
        }
    health_critical = _jsonsafe(
        _cap([c for c in critical if isinstance(c, dict)], _MAX_CRITICAL))

    signals = SimpleNamespace(
        priority_action=priority_action,
        health_critical=health_critical,
    )
    # Continuity comes from conversation history now (not the standing context).
    return signals, None
