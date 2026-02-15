"""
DBE — Briefing Ranker.

Scores and sorts selected briefing items for display order.
Factors: priority level, confidence score, recency.
"""

import logging

logger = logging.getLogger(__name__)


def rank_briefing_items(items):
    """
    Rank briefing items by composite score for display order.

    Args:
        items: list of dicts from briefing_selector (with type, title,
               message, priority, confidence, source_id, module).

    Returns:
        list of dicts sorted by rank (highest priority first).
    """
    if not items:
        return []

    scored = []
    for item in items:
        score = _compute_rank_score(item)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored]


def _compute_rank_score(item):
    """
    Compute a numeric rank score (lower = higher priority).

    Factors:
    - Priority: direct mapping (1 = highest)
    - Confidence: higher confidence = lower score (predictions)
    - Type boost: guidance > prediction > insight (for same priority)
    """
    priority = item.get("priority", 4)
    confidence = item.get("confidence") or 0.5
    item_type = item.get("type", "insight")

    # Base score from priority (10 points per level)
    base = priority * 10

    # Confidence bonus (0-5 points off for high confidence)
    confidence_bonus = (1 - confidence) * 5

    # Type tiebreaker
    type_offset = {
        "guidance": 0,
        "prediction": 1,
        "insight": 2,
    }.get(item_type, 3)

    return base + confidence_bonus + type_offset
