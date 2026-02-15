"""
WIRE — Report Ranker.

Ranks selected items by priority, confidence, magnitude, and recency.
"""

import logging

logger = logging.getLogger(__name__)


def rank_report_items(items):
    """
    Rank selected report items.

    Scoring:
    - Priority: (6 - priority) * 10 → 50/40/30/20/10
    - Confidence: confidence * 8 → 0-8 points
    - Type bonus: prediction=5, insight=3, state_change=2, guidance=1

    Args:
        items: List of selected item dicts.

    Returns:
        List of items sorted by score descending.
    """
    if not items:
        return []

    scored = []
    for item in items:
        score = _compute_score(item)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def _compute_score(item):
    """Compute ranking score for a report item."""
    score = 0.0

    # Priority contribution
    priority = item.get("priority", 5)
    score += (6 - priority) * 10

    # Confidence contribution
    confidence = item.get("confidence", 0)
    if confidence:
        score += confidence * 8

    # Type bonus
    item_type = item.get("type", "")
    type_bonuses = {
        "prediction": 5,
        "insight": 3,
        "state_change": 2,
        "guidance_acted": 1,
    }
    score += type_bonuses.get(item_type, 0)

    return score
