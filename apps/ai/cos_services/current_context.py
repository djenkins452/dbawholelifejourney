# ==============================================================================
# File: apps/ai/cos_services/current_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context baseline (Pillar 4) — the minimal always-on projection
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Current Context baseline — Pillar 4 of the WLJ ↔ model interface.

docs/WLJ_MODEL_INTERFACE_DESIGN.md §Pillar 4.

Current Context answers "what does the model need to know RIGHT NOW?" — and that is
mostly CONVERSATIONALLY relevant, so most of it is MODEL-PULLED via truth tools. This
module builds only the *minimal always-on baseline* — the few things the model cannot
know it needs, or must be told regardless of topic:

    * clock            — current local time + part of day  (the model can't know it)
    * day_continuity   — orient / reorient / continue + material changes since last turn
    * clinical_safety  — deterministic executive POLICY (e.g. an overdue medication);
                         the model must HONOR this order, never re-rank it
    * capabilities     — what truth WLJ can answer (so the model knows what to pull)

Deliberately EXCLUDED (this is reasoning, the model authors it): headline, narrative,
diagnosis, coaching, mood read. The baseline ships facts + deterministic policy only.

REQUEST-PATH-SAFE BY CONSTRUCTION: this is a pure ASSEMBLER. It never live-computes the
heavy executive picture — the caller passes an already-warmed `signals`
(ExecutiveSignals) and `continuity` (day-continuity Decision); when they are absent the
corresponding section is returned as `pending` (never a live rebuild). Clock and
capabilities are cheap/static.
"""

import logging

from apps.ai.cos_services.serialization import cap as _cap
from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

CURRENT_CONTEXT_SCHEMA_VERSION = "1.0"

_MAX_SAFETY = 5
_MAX_CHANGES = 6


def _clock(user, now=None) -> dict:
    """User-local time + part of day. Cheap + deterministic; never raises."""
    try:
        from apps.core.truth import daypart
        if now is None:
            from apps.core.utils import get_user_now
            now = get_user_now(user)
        local_time = now.strftime("%I:%M %p").lstrip("0")
        return {
            "local_time": local_time,
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


def _clinical_safety(signals) -> dict:
    """Deterministic executive POLICY the model must honor (not re-rank).

    Populated from an already-computed ExecutiveSignals; `pending` if not supplied.
    """
    if signals is None:
        return {"status": "pending"}
    health_critical = getattr(signals, "health_critical", None) or []
    priority_action = getattr(signals, "priority_action", None)
    return {
        "status": "ok",
        "clinical_safety": _jsonsafe(_cap(list(health_critical), _MAX_SAFETY)),
        "priority_action": _jsonsafe(priority_action),
        "note": "deterministic executive policy — honor this order; do not re-rank it",
    }


def _day_continuity(continuity) -> dict:
    """Orient / reorient / continue + material changes; `pending` if not supplied."""
    if continuity is None:
        return {"status": "pending"}
    return {
        "status": "ok",
        "mode": getattr(continuity, "mode", None),
        "material_changes": _jsonsafe(
            _cap(list(getattr(continuity, "material_changes", []) or []), _MAX_CHANGES)
        ),
    }


def get_current_context_baseline(user, *, signals=None, continuity=None, now=None) -> dict:
    """Assemble the minimal always-on Current Context baseline (Pillar 4).

    Pure assembly over pre-warmed inputs — no live heavy compute, no reasoning, no
    headline. `signals` / `continuity` are supplied by the warm caller; when absent the
    corresponding section is `pending`.
    """
    return {
        "schema_version": CURRENT_CONTEXT_SCHEMA_VERSION,
        "clock": _clock(user, now=now),
        "priority": _clinical_safety(signals),
        "day_continuity": _day_continuity(continuity),
        "capabilities": _capabilities(),
        # NOTE: intentionally NO 'headline'/'narrative' — that is the model's to author.
    }
