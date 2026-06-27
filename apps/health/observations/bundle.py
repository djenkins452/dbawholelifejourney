"""
Observation bundle — the single cached computation for the observation layers
(Sprint 9A performance hardening).

Sprints 5–8 computed observations → prioritization → narration inline in
``build_medicine_state`` (request path) and recomputed them again for the
physician summary. This consolidates all of it into ONE computation, cached per
user with a short TTL using the existing Django cache (no parallel framework),
and invalidated when the MedicationEvent ledger changes. Both the SAE medicine
state and the physician summary read this bundle.

Caching here is the standard mitigation for per-user derived analytics: the
ledger changes rarely, so a short TTL is safe, and a ledger write busts the cache
immediately (so freshness is event-driven, not poll-driven).
"""

import logging

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_PREFIX = "wlj:med:obs:"
OBS_TTL = 300  # seconds (5 min); busted immediately on a ledger write.


def _cache_key(user_id):
    return f"{CACHE_PREFIX}{user_id}"


def compute_observation_bundle(user):
    """Compute the full observation bundle (no cache). Deterministic."""
    from apps.health.observations.core import approve
    from apps.health.observations.narration import render_narration
    from apps.health.observations.prioritization import (
        group_observations,
        prioritize_observations,
    )
    from apps.health.observations.prioritization import build_context
    from apps.health.observations.rules import (
        cross_domain_observations,
        medication_observations,
    )

    raw = medication_observations(user) + cross_domain_observations(user)
    approved = approve(raw)
    observations = [o.to_dict() for o in approved]

    context = build_context(user)
    prioritized = prioritize_observations(approved, context)
    groups = group_observations(prioritized)

    narrations = [render_narration(d).to_dict() for d in prioritized]
    nar_by_key = {
        (d["type"], ":".join(sorted(d["domains"]))): n
        for d, n in zip(prioritized, narrations)
    }
    narration_groups = []
    for g in groups:
        items = [
            nar_by_key[(d["type"], ":".join(sorted(d["domains"])))]
            for d in g["observations"]
            if (d["type"], ":".join(sorted(d["domains"]))) in nar_by_key
        ]
        narration_groups.append({
            "key": g["key"], "title": g["title"],
            "physician_discussion": g["physician_discussion"],
            "narrations": items,
        })

    return {
        "observations": observations,
        "prioritized_observations": prioritized,
        "observation_groups": groups,
        "narrations": narrations,
        "narration_groups": narration_groups,
        "computed_at": timezone.now().isoformat(),
        "stats": {
            "raw": len(raw),
            "approved": len(observations),
            "suppressed": max(0, len(raw) - len(observations)),
            "physician_flagged": sum(1 for n in narrations if n["physician_discussion"]),
        },
    }


def get_observation_bundle(user, *, use_cache=True):
    """Return the observation bundle, cached per user (Sprint 9A).

    Read-from-cache first; compute + cache on miss. Resilient: any failure returns
    a safe empty bundle (fail-open to a neutral surface, never an exception that
    breaks the whole medicine state — Sprint 9C)."""
    key = _cache_key(user.id)
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached
    try:
        bundle = compute_observation_bundle(user)
    except Exception:
        logger.warning("Observation bundle computation failed for user %s",
                       user.id, exc_info=True)
        return _empty_bundle()
    cache.set(key, bundle, OBS_TTL)
    return bundle


def invalidate_observation_bundle(user_id):
    """Bust the cached bundle (called when the MedicationEvent ledger changes)."""
    try:
        cache.delete(_cache_key(user_id))
    except Exception:  # pragma: no cover - cache hiccup must never break a write
        logger.debug("Observation bundle invalidation failed", exc_info=True)


def _empty_bundle():
    return {
        "observations": [], "prioritized_observations": [],
        "observation_groups": [], "narrations": [], "narration_groups": [],
        "computed_at": timezone.now().isoformat(),
        "stats": {"raw": 0, "approved": 0, "suppressed": 0, "physician_flagged": 0},
    }
