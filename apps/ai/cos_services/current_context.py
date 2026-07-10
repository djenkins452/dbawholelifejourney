# ==============================================================================
# File: apps/ai/cos_services/current_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context baseline (Pillar 4) — the FAST tier: "what's happening now"
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Current Context — Pillar 4 of the WLJ ↔ model interface.

Current Context answers ONE question: "What is happening right now?" — the FAST-refresh
tier (seconds): the clock, the current WLJ page/screen the user is viewing, the active
task/selection, and a capability index. It changes constantly.

Current Context does NOT own deterministic understanding. Executive/clinical priority,
momentum, workload, patterns, material changes, etc. are DETERMINISTIC UNDERSTANDING —
the assessment tier of Truth (`apps/ai/model_interface/understanding.py`), a separate
owner with its own (medium) cadence. Refresh cadence is an ownership boundary
(Architecture Law) — we do not combine fast and medium concerns into one owner.

REQUEST-PATH-SAFE: everything here is cheap/deterministic (clock, static catalog,
client-supplied structured page context). No heavy compute, no warm needed.

`page_context` is the STRUCTURED WLJ page state the app already has (which page/entity the
user is viewing) — NOT a screenshot, NOT OCR. If the app provides it, the model sees it.
"""

import logging

logger = logging.getLogger(__name__)

CURRENT_CONTEXT_SCHEMA_VERSION = "2.0"


def _clock(user, now=None) -> dict:
    """User-local time + part of day. Cheap + deterministic; never raises."""
    try:
        from apps.core.truth import daypart
        if now is None:
            from apps.core.utils import get_user_now
            now = get_user_now(user)
        return {
            "local_time": now.strftime("%I:%M %p").lstrip("0"),
            "part_of_day": daypart.phase_of_day(user, now),
            "as_of": now.isoformat(),
        }
    except Exception:  # pragma: no cover - defensive
        logger.warning("CurrentContext: clock unavailable for user=%s",
                       getattr(user, "id", "?"))
        return {"status": "pending"}


def _capabilities() -> dict:
    """What truth WLJ can deterministically answer (static; no user data)."""
    try:
        from apps.core.truth import catalog
        cat = catalog.truth_catalog()
        domains = sorted(cat.keys()) if isinstance(cat, dict) else []
    except Exception:  # pragma: no cover - defensive
        domains = []
    return {
        "answerable_domains": domains,
        "note": "call a truth tool for anything not present in this baseline",
    }


def _current_screen(page_context) -> dict:
    """The structured WLJ page the user is currently viewing (client-supplied). This is
    WLJ state the app already has — treat a missing field as a possible sync issue, never
    as 'this information does not exist'."""
    if not page_context:
        return {"status": "none",
                "note": "no current page reported for this turn"}
    try:
        from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe
        return {"status": "present", "page": _jsonsafe(page_context)}
    except Exception:  # pragma: no cover - defensive
        return {"status": "none"}


def get_current_context_baseline(user, *, page_context=None, now=None) -> dict:
    """Assemble the fast-tier Current Context: clock, current screen, capability index.
    Pure, cheap, request-path-safe. No deterministic understanding here (that is a
    separate owned interface)."""
    return {
        "schema_version": CURRENT_CONTEXT_SCHEMA_VERSION,
        "clock": _clock(user, now=now),
        "current_screen": _current_screen(page_context),
        "capabilities": _capabilities(),
    }
