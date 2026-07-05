# ==============================================================================
# File: apps/ai/chatgpt_cos/executive_evidence.py
# TODAY'S CONVERSATION-REPORTED EVIDENCE — the "reported half" of the ONE executive
# picture. This is not a layer, engine, or capability; it is the per-day persistence
# of what the user TOLD Beth today (accomplishments, subjective state) that never lands
# in the deterministic SAE. `executive_interpretation.interpret()` reads this and MERGES
# it with deterministic truth into a single ExecutiveSignals — so every consumer
# (Morning Brief, Decision Support, Executive Summary, Goal Review, …) reflects the same
# evolving understanding without independently reading caches or rebuilding today's state.
#
# One brain: deterministic truth (SAE/tasks) + reported evidence (here) → interpret() →
# ExecutiveSignals → consumers.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)


def _key(user):
    from apps.core.utils import get_user_today
    return f"wlj:exec_evidence:{user.id}:{get_user_today(user).isoformat()}"


def _get(user):
    from django.core.cache import cache
    return dict(cache.get(_key(user)) or {})


def _set(user, data):
    from django.core.cache import cache
    cache.set(_key(user), data, 22 * 3600)


def record_accomplishment(user, label):
    """Record a mission-significant accomplishment the user reported today."""
    if not label:
        return
    try:
        d = _get(user)
        items = list(d.get("accomplishments") or [])
        if label not in items:
            items.append(label)
        d["accomplishments"] = items
        _set(user, d)
    except Exception:
        logger.warning("executive_evidence: record_accomplishment failed", exc_info=True)


def record_subjective(user, polarity):
    """Record the user's reported subjective energy today ('positive'/'negative').
    Latest report wins — it evolves as the day goes on."""
    if not polarity:
        return
    try:
        d = _get(user)
        d["subjective"] = polarity
        _set(user, d)
    except Exception:
        logger.warning("executive_evidence: record_subjective failed", exc_info=True)


def record_deferral(user, item, reason="", resume=""):
    """EXECUTIVE STATE RECONCILIATION — record that the user supplied trustworthy
    evidence today that a surfaced/routine item is NOT appropriate right now (already
    done / done recently / wrong time of day / canceled / traveling / sick). `item` is a
    short label (e.g. "Shower"), `reason` the WHY, `resume` when to pick it back up. The
    latest report for an item wins. interpret() reads these and folds them into the ONE
    picture so every consumer stops treating the item as today's priority."""
    if not item:
        return
    try:
        d = _get(user)
        defs = [x for x in (d.get("deferrals") or [])
                if (x.get("item") or "").strip().lower() != item.strip().lower()]
        defs.append({"item": item.strip(), "reason": (reason or "").strip(),
                     "resume": (resume or "").strip()})
        d["deferrals"] = defs
        _set(user, d)
    except Exception:
        logger.warning("executive_evidence: record_deferral failed", exc_info=True)


def deferred_labels(user):
    """Lowercased set of item labels the user has deferred out of today — the read
    every consumer uses to stop surfacing a reconciled item."""
    try:
        return {(x.get("item") or "").strip().lower()
                for x in (_get(user).get("deferrals") or []) if x.get("item")}
    except Exception:
        return set()


def today(user):
    """Today's reported evidence: {'accomplishments': [...], 'subjective': str|None,
    'deferrals': [{item, reason, resume}, ...]}."""
    try:
        d = _get(user)
        return {"accomplishments": list(d.get("accomplishments") or []),
                "subjective": d.get("subjective"),
                "deferrals": list(d.get("deferrals") or [])}
    except Exception:
        return {"accomplishments": [], "subjective": None, "deferrals": []}
