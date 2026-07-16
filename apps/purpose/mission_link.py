# ==============================================================================
# File: apps/purpose/mission_link.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Mission Link — the deterministic RELATIONSHIP between an action and the
#              user's long-term missions. A join + a rank. NOT an intelligence engine.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-10
# ==============================================================================
"""
Mission Link — deterministic truth: "what mission does this action support, and how much?"

BOUNDARY (fixed): WLJ owns the deterministic RELATIONSHIP; OpenAI owns what it MEANS.

This is a JOIN, not an engine:
    action --(production registry)--> signal_type --(GoalSignalSource)--> active goals
Ranked deterministically (Primary Mission first, then contribution weight descending).

It reuses the truth WLJ already models — `LifeGoal` (`is_primary_mission`, `why_it_matters`,
`success_looks_like`, `target_date`, `status`), `GoalSignalSource` (goal↔signal_type↔weight),
`select_active_mission_goal`, and the nightly `GoalMomentumSnapshot` — and introduces NO
competing taxonomy. It is domain-agnostic (a workout, a prayer, a journal entry, a
medication all resolve through the same `signal_type` join) and adjacent to Execution
Truth (never owned by it), so every consumer — dashboard, check-ins, OpenAI, notifications,
voice, executive summaries — reads the same relationship.

It returns ONLY deterministic values — references, strings, numbers, booleans, dates,
weights, calculated progress. It emits NO judgment: no "On Track", "At Risk", "Important",
no motivational language, no pace labels. OpenAI draws those conclusions from these facts.

The per-user mission MAP is user-stable → computed once, cached, invalidated on goal /
signal / primary / status / weight change (see apps/purpose/signals.py).
"""

import logging

logger = logging.getLogger(__name__)

_CACHE_KEY = "wlj:mission_map:{uid}"
_CACHE_TTL = 3600  # stable; invalidated on change, so TTL is only a backstop


# ── PRODUCTION registry: entity/execution-action → signal_type ───────────────
# Declarative and domain-agnostic. Resolution order: source-type override →
# title keyword → domain fallback. A new entity is one row, never a code branch.
# `signal_type` is the SAME universal contract goals consume (GoalSignalSource);
# this introduces no new taxonomy.
_SOURCE_TYPE_SIGNAL = {
    "medication_dose": "medication_adherence",
    "supplement_dose": "medication_adherence",
}
_KEYWORD_SIGNAL = (
    (("workout", "exercise", "gym", "run", "running", "lift", "cardio",
      "training", "fitness", "walk", "steps", "yoga", "stretch"), "health_activity"),
    (("prayer", "bible", "scripture", "devotion", "worship", "sermon",
      "gospel"), "faith_practice"),
    (("journal", "reflect", "gratitude", "diary"), "mental_reflection"),
    (("meditat", "mindful", "breath"), "mental_reflection"),
)
_DOMAIN_SIGNAL = {
    "health": "health_activity",
    "faith": "faith_practice",
    "journal": "mental_reflection",
    "mind": "mental_reflection",
    "work": "productivity_progress",
    "finance": "financial_health",
    "relationships": "relational_engagement",
}


def classify_signal_type(item):
    """Deterministic entity/action → `signal_type`, or None when unmapped.

    Never fabricates: an unmapped entity resolves to None (and therefore to no mission
    relationship) rather than being forced onto a signal. `item` is a dict-shaped action
    or entity carrying some of: source_type/source, title/name, domain."""
    if not isinstance(item, dict):
        return None
    src = (item.get("source_type") or item.get("source") or "").lower()
    if src in _SOURCE_TYPE_SIGNAL:
        return _SOURCE_TYPE_SIGNAL[src]
    name = (item.get("title") or item.get("name") or "").lower()
    for keywords, signal in _KEYWORD_SIGNAL:
        if any(k in name for k in keywords):
            return signal
    domain = (item.get("domain") or "").lower()
    return _DOMAIN_SIGNAL.get(domain)  # None when the domain is unmapped


# ── Per-user mission map (facts once) ────────────────────────────────────────
def _mission_facts(goal, today):
    """Deterministic facts for one mission. Progress is a CALCULATION; no pace labels."""
    target = getattr(goal, "target_date", None)
    try:
        milestone_percent = goal.milestone_progress_percent
    except Exception:  # pragma: no cover - defensive
        milestone_percent = None
    snap = None
    try:
        snap = goal.momentum_snapshots.first()  # nightly, read-only, latest by date
    except Exception:  # pragma: no cover - defensive
        snap = None
    return {
        "id": goal.id,
        "title": goal.title,
        "is_primary": bool(goal.is_primary_mission),
        "why_it_matters": (goal.why_it_matters_plain or "").strip(),
        "success_looks_like": (goal.success_looks_like_plain or "").strip(),
        "target_date": target.isoformat() if target else None,
        "days_to_target": (target - today).days if target else None,
        "progress": {
            # Numbers only — the conversational model decides "on track" / "behind".
            "milestone_percent": milestone_percent,
            "momentum_score": getattr(snap, "momentum_score", None) if snap else None,
            "progress_score": getattr(snap, "progress_score", None) if snap else None,
            "momentum_7d_avg": getattr(snap, "momentum_7d_avg", None) if snap else None,
        },
    }


def _build_mission_map(user):
    from django.utils import timezone

    from apps.purpose.models import LifeGoal

    today = timezone.localdate()
    # Active-goal contract: status='active' (paused/completed/released excluded).
    goals = list(
        LifeGoal.objects.filter(user=user, status="active")
        .prefetch_related("signal_sources")
    )

    missions = {}
    by_signal = {}
    primary_mission_id = None
    for goal in goals:
        missions[goal.id] = _mission_facts(goal, today)
        if goal.is_primary_mission:
            primary_mission_id = goal.id
        for src in goal.signal_sources.all():
            by_signal.setdefault(src.signal_type, []).append({
                "mission_id": goal.id,
                "weight": src.weight,
                "is_primary": bool(goal.is_primary_mission),
            })

    # Deterministic ranking per signal_type: Primary Mission first, then weight desc.
    for contribs in by_signal.values():
        contribs.sort(key=lambda c: (0 if c["is_primary"] else 1, -(c["weight"] or 0.0)))

    return {
        "missions": missions,
        "by_signal": by_signal,
        "primary_mission_id": primary_mission_id,
    }


def get_mission_map(user):
    """The user's mission map, computed once and cached. Shape:
        {"missions": {id: facts}, "by_signal": {signal_type: [ranked contribs]},
         "primary_mission_id": id|None}."""
    from django.core.cache import cache

    uid = getattr(user, "id", None)
    if not uid:
        return {"missions": {}, "by_signal": {}, "primary_mission_id": None}
    key = _CACHE_KEY.format(uid=uid)
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _build_mission_map(user)
    try:
        cache.set(key, data, _CACHE_TTL)
    except Exception:  # pragma: no cover - defensive
        pass
    return data


def invalidate_mission_map(user_id):
    """Drop the cached map for a user (called by goal/signal change signals)."""
    if not user_id:
        return
    try:
        from django.core.cache import cache
        cache.delete(_CACHE_KEY.format(uid=user_id))
    except Exception:  # pragma: no cover - defensive
        logger.debug("mission_link: cache invalidation skipped", exc_info=True)


# ── Resolution (the relationship) ────────────────────────────────────────────
def resolve_mission_link(user, *, signal_type=None, item=None, mission_map=None):
    """The deterministic mission relationship for a signal_type (or an action to classify).

    Returns references + facts only — NO mission prose (that lives once in the map):
        {"signal_type", "mission_id" (top), "weight", "is_primary",
         "contributes_to": [mission_id, ...]}   # ranked: primary first, then weight desc
    Returns None when the entity is unmapped OR no active goal consumes the signal — a
    real absence, never a fabricated relationship."""
    if signal_type is None and item is not None:
        signal_type = classify_signal_type(item)
    if not signal_type:
        return None
    mm = mission_map if mission_map is not None else get_mission_map(user)
    contribs = mm.get("by_signal", {}).get(signal_type)
    if not contribs:
        return None
    top = contribs[0]
    return {
        "signal_type": signal_type,
        "mission_id": top["mission_id"],
        "weight": top["weight"],
        "is_primary": top["is_primary"],
        "contributes_to": [c["mission_id"] for c in contribs],
    }


def enrich_action(user, action, mission_map=None):
    """Attach `signal_type` + `mission_link` REFERENCES to an execution action dict.
    Non-mutating (returns a shallow copy). Carries references, never duplicated mission
    prose — the full facts live once in the map's `missions` section."""
    if not isinstance(action, dict):
        return action
    mm = mission_map if mission_map is not None else get_mission_map(user)
    signal_type = classify_signal_type(action)
    link = resolve_mission_link(user, signal_type=signal_type, mission_map=mm) if signal_type else None
    out = dict(action)
    out["signal_type"] = signal_type
    out["mission_link"] = link
    return out
