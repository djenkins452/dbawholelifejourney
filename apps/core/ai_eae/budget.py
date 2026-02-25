"""
EAE — Noise Budget Engine (Phase 8.3).

Enforces per-channel cognitive unit caps with capacity adjustment.
Hard cap surfaced insights to 3–5 "cognitive units" per interaction.

Budget rules:
    - Per-channel defaults (chat=3, push=1, briefing=5, etc.)
    - Capacity adjustments (CRITICAL=-2, LOW=-1, HIGH=+1)
    - Hard maximums that capacity bonus cannot exceed
    - Floor of 1 (always surface at least the top priority)
    - Global daily budget of 8 across all channels
"""
import logging
from typing import Dict, List, Tuple

from apps.core.ai_eae.bundler import CognitiveUnit
from apps.core.ai_eae.constants import (
    BUDGET_FLOOR,
    BUDGET_GLOBAL_DAILY,
    CAPACITY_CRITICAL_ADJUSTMENT,
    CAPACITY_CRITICAL_THRESHOLD,
    CAPACITY_HIGH_ADJUSTMENT,
    CAPACITY_HIGH_THRESHOLD,
    CAPACITY_LOW_ADJUSTMENT,
    CAPACITY_LOW_THRESHOLD,
    CAPACITY_NORMAL_ADJUSTMENT,
    CHANNEL_BUDGET_MAP,
    CHANNEL_BUDGET_MAX_MAP,
    CHANNEL_CONFIDENCE_MAP,
    apply_intensity,
)

logger = logging.getLogger(__name__)


def _get_capacity_adjustment(capacity_score: float, intensity: float = 1.0) -> int:
    """
    Compute budget adjustment based on user's capacity score.

    Higher intensity compresses budgets more aggressively at low capacity.
    """
    if capacity_score < apply_intensity(CAPACITY_CRITICAL_THRESHOLD, intensity, inverse=True):
        return CAPACITY_CRITICAL_ADJUSTMENT
    elif capacity_score < apply_intensity(CAPACITY_LOW_THRESHOLD, intensity, inverse=True):
        return CAPACITY_LOW_ADJUSTMENT
    elif capacity_score > CAPACITY_HIGH_THRESHOLD:
        return CAPACITY_HIGH_ADJUSTMENT
    return CAPACITY_NORMAL_ADJUSTMENT


def compute_budget(
    channel: str,
    capacity_score: float = 0.5,
    daily_used: int = 0,
    intensity: float = 1.0,
) -> int:
    """
    Compute the cognitive unit budget for a channel.

    Args:
        channel: Channel identifier (chat, push, briefing, etc.)
        capacity_score: User's current capacity (0.0–1.0)
        daily_used: Cognitive units already consumed today
        intensity: Intensity multiplier

    Returns:
        Number of cognitive units allowed for this interaction.
    """
    base = CHANNEL_BUDGET_MAP.get(channel, 3)
    hard_max = CHANNEL_BUDGET_MAX_MAP.get(channel, 5)

    # Capacity adjustment
    adjustment = _get_capacity_adjustment(capacity_score, intensity)
    budget = base + adjustment

    # Clamp to [floor, hard_max]
    budget = max(BUDGET_FLOOR, min(hard_max, budget))

    # Global daily budget enforcement
    daily_remaining = max(0, BUDGET_GLOBAL_DAILY - daily_used)
    if channel != 'command_center':  # Command center is unlimited
        budget = min(budget, daily_remaining)

    # Ensure floor (always at least 1 unless daily budget exhausted AND not critical)
    budget = max(BUDGET_FLOOR, budget) if daily_remaining > 0 else max(0, budget)

    return budget


def apply_confidence_filter(
    units: List[CognitiveUnit],
    channel: str,
) -> List[CognitiveUnit]:
    """
    Filter out units below the minimum confidence threshold for a channel.
    """
    min_conf = CHANNEL_CONFIDENCE_MAP.get(channel, 0.4)
    if min_conf <= 0:
        return units

    filtered = [u for u in units if u.confidence >= min_conf]

    removed = len(units) - len(filtered)
    if removed > 0:
        logger.debug(
            "EAE budget: Removed %d low-confidence units (min=%.2f for %s)",
            removed, min_conf, channel,
        )

    return filtered


def apply_budget(
    units: List[CognitiveUnit],
    channel: str,
    capacity_score: float = 0.5,
    daily_used: int = 0,
    intensity: float = 1.0,
) -> Tuple[List[CognitiveUnit], List[Dict], int]:
    """
    Apply noise budget to cognitive units.

    Args:
        units: Cognitive units sorted by score descending.
        channel: Delivery channel.
        capacity_score: User's current capacity.
        daily_used: Units already consumed today.
        intensity: Intensity multiplier.

    Returns:
        Tuple of:
        - surfaced: List of CognitiveUnit that pass the budget
        - suppressed: List of dicts describing suppressed items
        - budget: The computed budget that was applied
    """
    if not units:
        return [], [], 0

    # Compute budget
    budget = compute_budget(channel, capacity_score, daily_used, intensity)

    # Confidence filter first
    units = apply_confidence_filter(units, channel)

    # Apply budget cap
    surfaced = units[:budget]
    suppressed_units = units[budget:]

    # Assign ranks
    for i, unit in enumerate(surfaced, 1):
        unit.rank = i

    # Build suppression audit trail
    suppressed = []
    for unit in suppressed_units:
        suppressed.append({
            'unit_id': unit.unit_id,
            'title': unit.title,
            'engine': unit.source_engine,
            'module': unit.module,
            'score': round(unit.normalized_score, 2),
            'reason': 'BUDGET_CAP',
        })

    logger.debug(
        "EAE budget: %s channel, budget=%d, surfaced=%d, suppressed=%d",
        channel, budget, len(surfaced), len(suppressed),
    )

    return surfaced, suppressed, budget
