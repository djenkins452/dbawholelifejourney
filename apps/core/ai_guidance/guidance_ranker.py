"""
PGE -- Guidance Ranker.

Ranks guidance candidates by multiple signals and returns the top items.

Ranking factors (in order of importance):
1. Priority (1=Critical, 5=Info — lower number = higher priority)
2. Prediction confidence (higher = more important)
3. Severity of source insight (warning > info > positive)
4. Recency (newer data preferred)
"""

import logging

logger = logging.getLogger(__name__)

# Maximum guidance items to surface per user
MAX_GUIDANCE_ITEMS = 5

# Severity weights for ranking within same priority
SEVERITY_WEIGHTS = {
    "critical": 4,
    "warning": 3,
    "info": 2,
    "positive": 1,
}


def rank_guidance(candidates, limit=MAX_GUIDANCE_ITEMS):
    """
    Rank and limit guidance candidates.

    Args:
        candidates: List of guidance candidate dicts.
        limit: Maximum items to return.

    Returns:
        List of top-ranked guidance candidates (sorted best-first).
    """
    if not candidates:
        return []

    # Score each candidate
    scored = []
    for candidate in candidates:
        score = _compute_rank_score(candidate)
        scored.append((score, candidate))

    # Sort by score descending (higher = more important)
    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top items
    return [candidate for _, candidate in scored[:limit]]


def _compute_rank_score(candidate):
    """
    Compute a composite ranking score for a candidate.

    Higher score = more important.
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

    return score
