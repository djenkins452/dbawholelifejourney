# ==============================================================================
# File: apps/ai/cos_services/standing_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: StandingContextService — the always-loaded ChatGPT CoS context
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
StandingContextService (ChatGPT CoS — Phase 1)
==============================================

Exposes the *minimum always-loaded context package* (see
@WLJ_SYSTEM_PROMPTS/07_DAY1_TOOL_CATALOG/02_Always_Loaded_Context_Specification.md)
as one compact, JSON-safe object the ChatGPT reasoning layer carries on every turn.

Design rules honored (Architecture Laws + WLJ performance law):
* REUSE ONLY — projects the existing `cos_context` / `executive` objects. No new
  intelligence, no re-aggregation (Law 9: State-First Reads).
* CACHE-FIRST, NEVER LIVE-COMPUTE on the request path. Reads the pre-warmed
  `cos_context` from `readiness_cache`; on a miss returns a `pending` shell
  (the keep-alive prewarm repopulates the cache shortly). `allow_build=True` is
  reserved for background/warming callers, never the request path.
* DETERMINISTIC + READ-ONLY. The LLM narrates this; it never originates it (Law 1).
* Wrappable later by an authenticated HTTP endpoint with zero logic change.

Public API:
    get_standing_context(user, *, page_context=None, allow_build=False) -> dict
"""

import logging
import time

from django.utils import timezone

from apps.ai.cos_services.serialization import cap as _cap
from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

STANDING_CONTEXT_SCHEMA_VERSION = "1.0"

# Cap list-valued fields so the always-loaded package stays token-cheap.
_MAX_SIGNALS = 8
_MAX_EVENTS = 6
_MAX_PRIORITIES = 6


# ---------------------------------------------------------------------------
# Personalization (cheap, single-row reads — safe on any path)
# JSON-safety helpers (jsonsafe / cap) are imported from .serialization.
# ---------------------------------------------------------------------------
def _cos_name(user):
    """Resolve the user-configured assistant name (default 'Chief of Staff')."""
    try:
        prefs = getattr(user, "preferences", None)
        if prefs is not None and hasattr(prefs, "get_cos_name"):
            return prefs.get_cos_name()
        if prefs is not None:
            return getattr(prefs, "cos_display_name", "") or "Chief of Staff"
    except Exception:
        logger.debug("standing_context: cos_name resolve failed", exc_info=True)
    return "Chief of Staff"


def _personalization(user, context):
    """Identity + enabled modules. Modules come from the context's own
    `module_permissions` (already computed) — no re-derivation."""
    modules = context.get("module_permissions") if context else None
    enabled = None
    if isinstance(modules, dict):
        enabled = sorted(k for k, v in modules.items() if v)
    return {
        "cos_name": _cos_name(user),
        "user_first_name": (getattr(user, "first_name", "") or None),
        "enabled_modules": enabled,
    }


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------
def _project_standing(user, context, *, source, build_ms, page_context):
    """
    Project an assembled cos_context into the standing-context package.

    Pure transformation over `context` + the `executive` projection. Every field
    is `.get()`-guarded so a missing key degrades to None/[] — present truth is
    surfaced, absent truth is omitted, nothing is fabricated.
    """
    # Derive the executive summary from the (possibly cached) context WITHOUT a
    # rebuild — build_executive_from_context is a pure projection.
    executive = {}
    try:
        from apps.core.ai_orchestrator.cos_context import (
            build_executive_from_context,
        )
        executive = build_executive_from_context(context) or {}
    except Exception:
        logger.warning(
            "standing_context: executive projection failed for user %s",
            getattr(user, "id", "?"),
            exc_info=True,
        )

    package = {
        "status": "ready",
        "schema_version": STANDING_CONTEXT_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "personalization": _personalization(user, context),
        # current_screen is the ONLY client-supplied field (PARTIAL — in-app only).
        "current_screen": page_context if page_context else None,
        "time": {
            "now": timezone.now().isoformat(),
            "day_significance": context.get("day_significance"),
            "right_now_focus": context.get("right_now_focus"),
        },
        # --- "what should I do / where do I stand" ---
        "execution_summary": context.get("execution_summaries"),
        "active_block": (context.get("right_now_focus") or {}).get("active_block")
        if isinstance(context.get("right_now_focus"), dict) else None,
        "capacity": context.get("capacity_snapshot"),
        # --- "how am I doing" (executive composed summary) ---
        "strategic_summary": executive.get("strategic_state_summary"),
        "top_risks": executive.get("risk_flags"),
        "momentum": executive.get("momentum_indicators"),
        "pressure": executive.get("pressure_indicators"),
        "health_summary": executive.get("health_status"),
        "relational_status": executive.get("relational_status"),
        "recommended_focus": executive.get("recommended_focus_for_today"),
        "current_mode": executive.get("tone_mode"),
        # --- "what's notable" (signals) ---
        "top_signals": _cap(context.get("top_signals"), _MAX_SIGNALS),
        "critical_signals": _cap(context.get("critical_signals"), _MAX_SIGNALS),
        # --- goals / priorities ---
        "priorities": _cap(context.get("user_priorities"), _MAX_PRIORITIES),
        # --- foundational domain headlines already in context ---
        "medication_adherence": context.get("medication_adherence_state"),
        "active_fast": context.get("active_fast_status"),
        "calendar_today": _cap(context.get("calendar_events_today"), _MAX_EVENTS),
        # --- composed standing CoS read ---
        "cos_intelligence": context.get("cos_intelligence"),
        # --- explicit gaps (do not imply truth that isn't computed) ---
        "travel_state": None,  # Travel is an unbuilt domain (ABSENT) — never inferred.
        # --- narration guard (Law 16) ---
        "trust_framing": (
            "Standing context is canonical SUMMARY state. Treat rollups as "
            "summaries, not per-item truth; confirm item-level claims "
            "(completed/overdue/next-action) via domain or decision tools."
        ),
        "_meta": {"source": source, "build_ms": build_ms},
    }
    return _jsonsafe(package)


def _pending_shell(user, page_context, *, reason="cache_miss"):
    """Returned when no pre-warmed context is available. Honors the WLJ rule:
    never live-compute on the request path — return 'pending', do not rebuild."""
    return {
        "status": "pending",
        "schema_version": STANDING_CONTEXT_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "personalization": _personalization(user, None),
        "current_screen": page_context if page_context else None,
        "reason": reason,
        "trust_framing": (
            "Standing context is warming. No deterministic state is available "
            "yet — do not infer current state; retry shortly."
        ),
        "_meta": {"source": "pending", "build_ms": None},
    }


# ---------------------------------------------------------------------------
# Telemetry (observable, lightweight)
# ---------------------------------------------------------------------------
def _emit(user_id, status, source, ms, field_count):
    try:
        logger.info(
            "STANDING_CTX served user=%s status=%s source=%s ms=%s fields=%s",
            user_id, status, source,
            ("%.1f" % ms) if ms is not None else "na", field_count,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_standing_context(user, *, page_context=None, allow_build=False):
    """
    Return the always-loaded ChatGPT CoS standing context for `user`.

    Cache-first: reads the pre-warmed `cos_context` from `readiness_cache`. On a
    miss, returns a `pending` shell unless `allow_build=True` (reserved for
    background/warming callers — NOT the request path), in which case it warms
    the cache via the existing `prewarm_cos_context`.

    Args:
        user: Django User instance.
        page_context: optional dict of client-supplied current-screen info
            (the only non-deterministic field; in-app only).
        allow_build: if True, build+cache on a miss (background callers only).

    Returns:
        dict — JSON-safe standing context. `status` is 'ready' or 'pending'.
    """
    t0 = time.monotonic()
    source = "cache"
    build_ms = None

    try:
        from apps.ai.readiness_cache import get_cached_cos_context
        context = get_cached_cos_context(user)
    except Exception:
        logger.warning("standing_context: cache read failed", exc_info=True)
        context = None

    if context is None and allow_build:
        try:
            from apps.ai.readiness_cache import prewarm_cos_context
            b0 = time.monotonic()
            context = prewarm_cos_context(user) or None
            build_ms = (time.monotonic() - b0) * 1000
            source = "build"
        except Exception:
            logger.warning(
                "standing_context: build failed for user %s",
                getattr(user, "id", "?"), exc_info=True,
            )
            context = None

    if context is None:
        shell = _pending_shell(user, page_context)
        _emit(getattr(user, "id", "?"), "pending", "pending", None, len(shell))
        return shell

    package = _project_standing(
        user, context, source=source, build_ms=build_ms,
        page_context=page_context,
    )
    total_ms = (time.monotonic() - t0) * 1000
    _emit(getattr(user, "id", "?"), "ready", source, total_ms, len(package))
    return package
