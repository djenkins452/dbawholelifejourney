"""
Chief of Staff — Operations Awareness banner (customer-language consumer).

This is a READ-ONLY consumer of the deterministic Operations truth. It creates
NO monitoring, NO scoring, NO incident lifecycle — it translates the already-
computed executive summary (``payload["executive"]`` under
``OPS_STREAM_CACHE_KEY``) into the customer-language state the pinned CoS banner
renders. Operations remains the single authority; this only communicates impact.

Product contract (WLJ "Operations is platform state, not conversation"):
  * HEALTHY   → no banner (returns state="healthy"; the UI shows nothing).
  * DEGRADED  → 🟡 reduced reliability; information safe.
  * CRITICAL  → 🔴 operational issue may affect new activity; existing data safe.
The banner copy is fixed, reassurance-first, and NEVER exposes infrastructure
terminology (ISE / SAME / OPS-1 / scheduler / Celery / Redis / Beat / drift /
queue / workers). The deterministic ``customer_impact_phrases`` feed only the
optional "Details" expansion, so specifics stay truthful without jargon.

Request-path safety: reads ONLY the pre-computed cache payload (never computes,
never rebuilds). Missing/pending payload fails SAFE to "healthy" (no banner).

Path: apps/ai/operations_banner.py
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The banner's single action target. A plain relative URL keeps it environment-
# agnostic (works in dev and prod); the Ops Wall itself is is_staff-gated.
OPS_WALL_URL = "/admin-console/ops/"

# Infra terms that must NEVER reach the customer-facing banner. Used by tests to
# assert the translation boundary holds; kept here as the single source.
FORBIDDEN_TERMS = (
    "ISE", "SAME", "OPS-1", "OPS ", "COAS", "Celery", "Redis", "Beat",
    "drift", "queue", "worker", "scheduler", "heartbeat", "gunicorn",
    "Postgres", "cache", "cron",
)


def _degraded_state():
    return {
        "state": "degraded",
        "emoji": "🟡",
        "title": "Operations Alert",
        "lines": [
            "WLJ is operating with reduced reliability.",
            "Background processing has slowed, which may delay reminders and AI insights.",
            "Your information is safe.",
        ],
        "action_label": "Open Operations Wall",
        "action_url": OPS_WALL_URL,
    }


def _critical_state():
    return {
        "state": "critical",
        "emoji": "🔴",
        "title": "Operations Alert",
        "lines": [
            "WLJ is experiencing an operational issue that may affect new activity.",
            "Existing information is safe.",
            "Some reminders and background processing may be delayed until the issue is resolved.",
        ],
        "action_label": "Open Operations Wall",
        "action_url": OPS_WALL_URL,
    }


def _healthy_state():
    # No banner. The UI consumes state == "healthy" to hide/clear the banner and
    # (on a non-healthy → healthy transition) show the transient recovered cue.
    return {
        "state": "healthy",
        "emoji": "🟢",
        "title": "",
        "lines": [],
        "action_label": "View Operations",
        "action_url": OPS_WALL_URL,
    }


def get_customer_operations_status():
    """Return the customer-language Operations banner state (request-path-safe).

    Reads ONLY the pre-computed ops stream payload from cache. Never computes,
    never rebuilds, never queries heavy state. Fails SAFE to healthy so a cold
    cache or a telemetry hiccup can never flash a false alarm at the customer.
    """
    try:
        from django.core.cache import cache
        from apps.core.ai_observability.ops_telemetry import OPS_STREAM_CACHE_KEY

        payload = cache.get(OPS_STREAM_CACHE_KEY) or {}
        executive = (payload.get("executive") or {}) if isinstance(payload, dict) else {}
        overall = str(executive.get("overall_status") or "HEALTHY").upper()

        if overall == "CRITICAL":
            state = _critical_state()
        elif overall == "DEGRADED":
            state = _degraded_state()
        else:
            state = _healthy_state()

        # Deterministic specifics for the OPTIONAL "Details" expansion only —
        # never the primary reassurance copy. Already customer-language.
        phrases = executive.get("customer_impact_phrases") or []
        state["impact_phrases"] = [str(p) for p in phrases][:4]
        return state
    except Exception as e:  # never let a telemetry read break the chat panel
        logger.warning("operations banner status read failed: %s", e)
        return _healthy_state()
