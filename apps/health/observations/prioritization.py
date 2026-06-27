"""
Deterministic Observation Prioritization (Sprint 6).

Decides WHICH approved observations matter most to this user and in WHAT order —
so Beth never has to. Fully deterministic and explainable: NO LLM ranking, no AI
heuristics, no recommendations. Identical input always yields identical ordering.

Pipeline:  approved observations + personal context → priority scores → grouping.
Does not change observation generation or safety classification (Sprint 5 owns those).
"""

# ── Deterministic base priority per observation type (6C) ─────────────────────
# Encodes the ranking rules: current risks > recent changes > opportunities >
# stable history (declining adherence 90 > improving 50; recent change 80 >
# stable 30 > long-term 25).
TYPE_BASE_PRIORITY = {
    "adherence_declining": 90,            # current risk
    "treatment_recently_changed": 80,
    "multiple_dose_increases": 70,
    "multiple_dose_reductions": 70,
    "weight_after_treatment_change": 65,
    "glucose_after_treatment_change": 65,
    "recent_provider_change": 55,
    "adherence_improving": 50,            # opportunity (below the risk)
    "exercise_during_treatment": 40,
    "recent_refill_pattern": 35,
    "medication_stable": 30,
    "long_term_stability": 25,
}
DEFAULT_BASE = 20

# ── Deterministic grouping (6D) ───────────────────────────────────────────────
TYPE_GROUP = {
    "adherence_declining": "adherence",
    "adherence_improving": "adherence",
    "treatment_recently_changed": "treatment_changes",
    "multiple_dose_increases": "treatment_changes",
    "multiple_dose_reductions": "treatment_changes",
    "weight_after_treatment_change": "treatment_response",
    "glucose_after_treatment_change": "treatment_response",
    "exercise_during_treatment": "treatment_response",
    "recent_provider_change": "logistics",
    "recent_refill_pattern": "logistics",
    "medication_stable": "stability",
    "long_term_stability": "stability",
}
GROUP_TITLES = {
    "adherence": "Adherence",
    "treatment_changes": "Recent treatment changes",
    "treatment_response": "Treatment response",
    "logistics": "Prescriptions & refills",
    "stability": "Treatment stability",
    "other": "Other",
}

# Deterministic per-type freshness — how long an observation stays relevant.
TYPE_EXPIRATION_DAYS = {
    "adherence_declining": 14,
    "adherence_improving": 14,
    "treatment_recently_changed": 21,
    "multiple_dose_increases": 60,
    "multiple_dose_reductions": 60,
    "weight_after_treatment_change": 60,
    "glucose_after_treatment_change": 60,
    "recent_provider_change": 45,
    "exercise_during_treatment": 45,
    "recent_refill_pattern": 30,
    "medication_stable": 90,
    "long_term_stability": 120,
}


def build_context(user):
    """Deterministic personal context from canonical sources (6B).

    Uses canonical utilities/models — never re-queries raw data where a canonical
    surface exists. Returns a plain dict for transparent ranking.
    """
    import logging
    logger = logging.getLogger(__name__)

    adherence = None
    goal_keywords = set()
    try:
        from apps.health.medicine_utils import calculate_medicine_adherence_rate
        adherence = calculate_medicine_adherence_rate(user, days=30)
    except Exception:
        logger.debug("context adherence failed", exc_info=True)
    try:
        from apps.purpose.models import LifeGoal
        for title in LifeGoal.objects.filter(
            user=user, status="active",
        ).values_list("title", flat=True)[:20]:
            for word in (title or "").lower().split():
                if len(word) >= 4:
                    goal_keywords.add(word)
    except Exception:
        logger.debug("context goals failed", exc_info=True)

    return {
        "adherence_30d": adherence,
        "has_adherence_issue": adherence is not None and adherence < 80,
        "goal_keywords": sorted(goal_keywords),
    }


def _matches_goal(obs, context):
    """Deterministic substring match of the observation against active goals."""
    kws = context.get("goal_keywords") or []
    if not kws:
        return False
    text = (obs.title + " " + obs.detail + " " + " ".join(obs.domains)).lower()
    return any(kw in text for kw in kws)


def _score(obs, context):
    """Deterministic priority score + explanation factors for one observation."""
    base = TYPE_BASE_PRIORITY.get(obs.type, DEFAULT_BASE)
    factors = [{"factor": "type_base", "value": base}]
    score = base

    # Confidence (high-confidence outranks moderate).
    conf_adj = round(obs.confidence * 20)
    score += conf_adj
    factors.append({"factor": "confidence", "value": conf_adj})

    # Evidence quality — more references, slightly higher (capped).
    ev_adj = min(10, len(obs.evidence) * 2)
    score += ev_adj
    factors.append({"factor": "evidence_quality", "value": ev_adj})

    # Physician-discussion urgency.
    if obs.physician_discussion:
        score += 15
        factors.append({"factor": "physician_discussion", "value": 15})

    # Goal relevance.
    relevant = _matches_goal(obs, context)
    if relevant:
        score += 20
        factors.append({"factor": "matches_active_goal", "value": 20})

    # Adherence-issue context lifts adherence-declining further.
    if obs.type == "adherence_declining" and context.get("has_adherence_issue"):
        score += 10
        factors.append({"factor": "active_adherence_issue", "value": 10})

    urgency = "high" if (obs.physician_discussion or score >= 80) else (
        "medium" if score >= 50 else "low"
    )
    relevance = "high" if relevant else ("medium" if score >= 50 else "low")
    explanation = (
        f"Base {base} for '{obs.type}'"
        + (" · high confidence" if conf_adj >= 16 else "")
        + (" · flagged for physician discussion" if obs.physician_discussion else "")
        + (" · relevant to an active goal" if relevant else "")
    )
    return score, factors, urgency, relevance, explanation


def prioritize_observations(observations, context):
    """Augment approved observations with deterministic priority fields and sort.

    Args:
        observations: approved Observation objects (post safety classifier).
        context: from build_context().
    Returns a list of dicts (observation + priority fields), highest priority first.
    Ordering is fully deterministic — score desc, then a stable (type, dedupe_key)
    tiebreak so identical input always produces identical ordering.
    """
    out = []
    for obs in observations:
        score, factors, urgency, relevance, explanation = _score(obs, context)
        d = obs.to_dict()
        d.update({
            "priority_score": score,
            "priority_explanation": explanation,
            "contributing_factors": factors,
            "urgency": urgency,
            "relevance": relevance,
            "expires_in_days": TYPE_EXPIRATION_DAYS.get(obs.type, 30),
            "group_key": TYPE_GROUP.get(obs.type, "other"),
        })
        out.append(d)
    out.sort(key=lambda d: (-d["priority_score"], d["type"],
                            ":".join(sorted(d["domains"]))))
    return out


def group_observations(prioritized):
    """Deterministically cluster prioritized observations (6D). Individual
    observations (with their evidence) are preserved under each cluster; the
    cluster takes the priority of its strongest member. No LLM grouping."""
    groups = {}
    for d in prioritized:
        key = d.get("group_key", "other")
        g = groups.setdefault(key, {
            "key": key,
            "title": GROUP_TITLES.get(key, GROUP_TITLES["other"]),
            "observations": [],
            "priority_score": 0,
            "physician_discussion": False,
        })
        g["observations"].append(d)
        g["priority_score"] = max(g["priority_score"], d["priority_score"])
        g["physician_discussion"] = g["physician_discussion"] or d["physician_discussion"]
    # Stable ordering: by cluster priority desc, then key.
    return sorted(groups.values(), key=lambda g: (-g["priority_score"], g["key"]))


def build_prioritized(user, observations=None):
    """Full deterministic prioritization pipeline. Returns
    (prioritized_observations, observation_groups)."""
    from apps.health.observations.engine import build_observations
    if observations is None:
        observations = build_observations(user)
    context = build_context(user)
    prioritized = prioritize_observations(observations, context)
    groups = group_observations(prioritized)
    return prioritized, groups
