"""
PGE -- Guidance Ranker.

Ranks guidance candidates by multiple signals and returns the top items.

Ranking factors (in order of importance):
1. Priority (1=Critical, 5=Info — lower number = higher priority)
2. Prediction confidence (higher = more important)
3. Severity of source insight (warning > info > positive)
4. Recency (newer data preferred)
5. User responsiveness (GLOE — gentle adjustment via learning profile)
"""

import logging

logger = logging.getLogger(__name__)

# Maximum guidance items to surface per user
MAX_GUIDANCE_ITEMS = 5

# GLOE responsiveness influence (0.25 = up to ±25% adjustment)
RESPONSIVENESS_INFLUENCE = 0.25

# Severity weights for ranking within same priority
SEVERITY_WEIGHTS = {
    "critical": 4,
    "warning": 3,
    "info": 2,
    "positive": 1,
}


def rank_guidance(candidates, limit=MAX_GUIDANCE_ITEMS, user=None):
    """
    Rank and limit guidance candidates.

    Args:
        candidates: List of guidance candidate dicts.
        limit: Maximum items to return.
        user: Optional Django User instance. If provided, GLOE
              responsiveness_score is factored into ranking.

    Returns:
        List of top-ranked guidance candidates (sorted best-first).
    """
    if not candidates:
        return []

    # Get GLOE responsiveness score if user provided
    responsiveness = _get_responsiveness(user) if user else None

    # Score each candidate
    scored = []
    for candidate in candidates:
        score = _compute_rank_score(candidate, responsiveness=responsiveness)
        scored.append((score, candidate))

    # Sort by score descending (higher = more important)
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top items
    return [candidate for _, candidate in scored[:limit]]


def _compute_rank_score(candidate, responsiveness=None):
    """
    Compute a composite ranking score for a candidate.

    Higher score = more important.

    Args:
        candidate: Guidance candidate dict.
        responsiveness: Optional GLOE responsiveness_score (0.0-1.0).
            If provided, gently adjusts the final score. A neutral value
            of 0.5 has no effect. Higher values boost, lower values reduce.
    """
    score = 0.0

    # Priority contribution (1=Critical→50pts, 5=Info→10pts)
    priority = candidate.get("priority", 3)
    score += (6 - priority) * 10  # 50, 40, 30, 20, 10

    # Confidence contribution (0-10 points)
    confidence = candidate.get("confidence_score")
    if confidence is not None:
        score += confidence * 10

    # Source contribution
    source = candidate.get("source", "")
    if source == "prie_prediction":
        score += 5  # Predictions are forward-looking, valuable
    elif source == "pie_insight":
        score += 3
    elif source == "sae_state":
        score += 2

    # Evidence richness (more evidence = more trustworthy)
    evidence = candidate.get("evidence", {})
    if evidence:
        score += min(3, len(evidence))  # Cap at 3 points

    # GLOE responsiveness adjustment (gentle — does NOT override priority)
    # responsiveness 0.5 = neutral (no change), 1.0 = +25%, 0.0 = -25%
    if responsiveness is not None:
        adjustment = (responsiveness - 0.5) * 2 * RESPONSIVENESS_INFLUENCE
        score *= (1 + adjustment)

    return score


def _get_responsiveness(user):
    """
    Get GLOE responsiveness score for user. Never breaks ranking.

    Returns:
        float or None — responsiveness score (0.0-1.0), or None if unavailable.
    """
    try:
        from apps.core.ai_guidance_learning.learning_engine import get_responsiveness_score
        return get_responsiveness_score(user)
    except Exception:
        return None
