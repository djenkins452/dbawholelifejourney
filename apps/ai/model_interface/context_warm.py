# ==============================================================================
# File: apps/ai/model_interface/context_warm.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Cache-first Current Context warming (Pillar 4 signals)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Current Context warming — the cache-first source of the deterministic policy the
model interface feeds into Pillar 4 (priority / clinical-safety / day-continuity).

Request-path safety (CLAUDE.md): `interpret()` is ~850ms (heavy) and MUST NOT run on
the request path. So:
  * `warm(user)`   — computes `interpret()` + day-continuity and CACHES a compact,
                     JSON-safe payload. Run by a background/warming caller (Celery
                     task, or the validation harness) — never the request path.
  * `read(user)`   — CACHE-FIRST read; returns `(signals, continuity)` lightweight
                     objects for `get_current_context_baseline`, or `(None, None)`
                     when cold (→ the baseline returns `pending`, honestly).

We cache only what Current Context consumes (priority_action, health_critical, and the
day-continuity mode + material_changes) — NOT the whole ExecutiveSignals, and never the
`headline` (that is reasoning the model authors).
"""

import logging
from types import SimpleNamespace

from django.core.cache import cache

from apps.ai.cos_services.serialization import jsonsafe as _jsonsafe

logger = logging.getLogger(__name__)

_TTL = 150  # seconds; a background warm keeps this fresh in prod


def _key(user_id):
    return f"wlj:mi:current_context:{user_id}"


def warm(user):
    """Compute + cache the Current Context policy payload. Heavy — background only.
    Returns the cached payload (or None on failure). Never raises."""
    uid = getattr(user, "id", None)
    try:
        from apps.ai.chatgpt_cos.executive_interpretation import interpret
        signals = interpret(user)
        payload = {
            "priority_action": _jsonsafe(getattr(signals, "priority_action", None)),
            "health_critical": _jsonsafe(getattr(signals, "health_critical", None) or []),
        }
    except Exception:
        logger.warning("mi.context_warm: interpret failed user=%s", uid, exc_info=True)
        payload = {"priority_action": None, "health_critical": []}

    try:
        from apps.ai.chatgpt_cos.day_continuity import assess
        decision = assess(user)
        payload["continuity"] = {
            "mode": getattr(decision, "mode", None),
            "material_changes": _jsonsafe(
                getattr(decision, "material_changes", None) or []),
        }
    except Exception:
        logger.warning("mi.context_warm: continuity failed user=%s", uid, exc_info=True)
        payload["continuity"] = None

    try:
        cache.set(_key(uid), payload, _TTL)
    except Exception:  # pragma: no cover - defensive
        logger.warning("mi.context_warm: cache set failed user=%s", uid, exc_info=True)
    return payload


def read(user):
    """Cache-first. Return (signals, continuity) lightweight objects for
    get_current_context_baseline, or (None, None) when cold. Never raises, never
    live-computes."""
    uid = getattr(user, "id", None)
    try:
        payload = cache.get(_key(uid))
    except Exception:  # pragma: no cover - defensive
        payload = None
    if not payload:
        return None, None

    signals = SimpleNamespace(
        priority_action=payload.get("priority_action"),
        health_critical=payload.get("health_critical") or [],
    )
    cont = payload.get("continuity")
    continuity = None
    if cont:
        continuity = SimpleNamespace(
            mode=cont.get("mode"),
            material_changes=cont.get("material_changes") or [],
        )
    return signals, continuity
