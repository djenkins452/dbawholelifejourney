"""
Whole Life Journey - Priority Engine

Project: Whole Life Journey
Path: apps/core/blueprint/priority_engine.py
Purpose: Tier-based priority system with conflict resolution

Description:
    Implements the shared "Priority Engine Contract" that all engines consult.
    Enforces the guardrail rule: Tier 1 is protected aggressively. Tier 1 can
    only be touched if all other options are exhausted, and must be explained
    via E3 with impact + recovery plan.

    Tiers:
        1 = Identity protected (user-selected)
        2 = Directional commitments (non-negotiables not in tier1)
        3 = Administrative (scheduled but flexible)
        4 = Optional

    Conflict Resolution:
        - Dominant rule: Protect Tier 1; move tiers 4→3→2 first
        - Touch Tier 1 only if ALL other options exhausted (Rule B)
        - If Tier 1 touched: MUST attach E3 explanation with identity cost + recovery plan

Public API:
    - resolve_conflict(blueprint, conflicting_blocks) -> ConflictResolution
    - compute_identity_cost(blueprint, behavior_key) -> float
    - get_tier_for_block(blueprint, block) -> int
    - prioritize_blocks(blueprint, blocks) -> sorted list

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class ConflictResolution:
    """Result of a conflict resolution operation."""
    success: bool
    moved_blocks: List[dict] = field(default_factory=list)
    tier1_impacted: bool = False
    identity_cost: float = 0.0
    recovery_plan: str = ''
    explanation: str = ''
    evidence: dict = field(default_factory=dict)


@dataclass
class IdentityCostResult:
    """Result of an identity cost computation."""
    cost: float  # 0-100
    pillar_weight: float
    frequency_violation_rate: float
    drift_delta: float
    explanation: str


# =============================================================================
# PUBLIC API
# =============================================================================


def resolve_conflict(blueprint, blocks_to_schedule, available_slots, curveball_block=None):
    """
    Resolve scheduling conflicts using tier-based priority.

    Strategy (Rule B):
    1. Try to fit curveball into empty slots
    2. Move Tier 4 blocks first
    3. Then Tier 3
    4. Then Tier 2
    5. Tier 1 ONLY if ALL others exhausted — with E3 explanation

    Args:
        blueprint: PersonalOperatingBlueprint
        blocks_to_schedule: List of ScheduledBlock-like dicts with 'tier', 'title', etc.
        available_slots: List of available time slots
        curveball_block: Optional new block that needs to be scheduled

    Returns:
        ConflictResolution
    """
    resolution = ConflictResolution(success=True)

    if curveball_block is None:
        return resolution

    # Sort existing blocks by tier (highest tier number = lowest priority = move first)
    sorted_blocks = sorted(blocks_to_schedule, key=lambda b: -b.get('tier', 4))

    moved = []
    tier1_touched = False

    for block in sorted_blocks:
        tier = block.get('tier', 4)

        if tier == 1:
            # Rule B: Only touch tier 1 if absolutely necessary
            if not moved:
                # No other blocks were movable — we must touch tier 1
                tier1_touched = True
                cost = compute_identity_cost(
                    blueprint,
                    block.get('behavior_key', ''),
                )
                resolution.tier1_impacted = True
                resolution.identity_cost = cost.cost
                resolution.recovery_plan = _generate_recovery_plan(
                    blueprint, block
                )
                resolution.explanation = (
                    f"Tier 1 behavior '{block.get('title', '')}' must be adjusted. "
                    f"Identity cost: {cost.cost:.0f}/100. {cost.explanation}"
                )
                resolution.evidence = {
                    'tier1_behavior': block.get('behavior_key', ''),
                    'identity_cost': cost.cost,
                    'pillar_weight': cost.pillar_weight,
                    'recovery_plan': resolution.recovery_plan,
                    'reason': 'all_other_tiers_exhausted',
                }
                moved.append({
                    'block': block,
                    'action': 'adjusted',
                    'tier': tier,
                })
            continue  # Skip tier 1 if other moves were available
        else:
            moved.append({
                'block': block,
                'action': 'moved',
                'tier': tier,
            })

    resolution.moved_blocks = moved

    if not tier1_touched:
        resolution.explanation = (
            f"Resolved conflict by moving {len(moved)} lower-priority blocks. "
            "Tier 1 behaviors preserved."
        )

    return resolution


def compute_identity_cost(blueprint, behavior_key):
    """
    Compute the identity cost (0-100) of impacting a behavior.

    Factors:
    - Pillar priority weight (from blueprint ranking)
    - Frequency violation rate (from drift history)
    - Predicted drift delta (from PRIE)
    """
    from .models import DriftEvent, DriftScore

    # Pillar weight
    pillar = _get_pillar_for_behavior(blueprint, behavior_key)
    pillar_weight = blueprint.get_pillar_weight(pillar) if pillar else 0.5

    # Frequency violation rate (last 14 days)
    from django.utils import timezone
    import datetime

    cutoff = timezone.now() - datetime.timedelta(days=14)
    drift_count = DriftEvent.objects.filter(
        user=blueprint.user,
        behavior_key=behavior_key,
        occurred_at__gte=cutoff,
    ).count()
    # Normalize: 0 events = 0, 7+ events in 14 days = 1.0
    freq_rate = min(1.0, drift_count / 7.0)

    # Drift delta (check latest score)
    latest_score = DriftScore.objects.filter(
        user=blueprint.user,
    ).order_by('-date').first()
    drift_delta = 0.0
    if latest_score:
        drift_delta = latest_score.drift_probability_24h

    # Weighted cost formula
    cost = (
        pillar_weight * 40 +  # 40% pillar importance
        freq_rate * 30 +       # 30% recent violations
        drift_delta * 30       # 30% predicted drift
    )

    explanation = (
        f"Pillar '{pillar}' weight={pillar_weight:.2f}, "
        f"recent violations={drift_count}/14d, "
        f"drift prediction={drift_delta:.2f}"
    )

    return IdentityCostResult(
        cost=min(100, max(0, cost)),
        pillar_weight=pillar_weight,
        frequency_violation_rate=freq_rate,
        drift_delta=drift_delta,
        explanation=explanation,
    )


def get_tier_for_block(blueprint, block_data):
    """
    Determine the tier for a scheduled block based on blueprint configuration.

    Args:
        blueprint: PersonalOperatingBlueprint
        block_data: dict with 'behavior_key', 'source', etc.

    Returns:
        int: tier level 1-4
    """
    behavior_key = block_data.get('behavior_key', '')
    source = block_data.get('source', '')

    if behavior_key:
        return blueprint.get_tier_for_behavior(behavior_key)

    # Source-based tier assignment
    source_tier_map = {
        'non_negotiable': 2,
        'calendar': 3,
        'task': 3,
        'health': 2,
        'sleep': 1,  # Sleep is always protected
        'buffer': 4,
    }
    return source_tier_map.get(source, 4)


def prioritize_blocks(blueprint, blocks):
    """
    Sort blocks by priority (tier 1 first, then by pillar weight).

    Args:
        blueprint: PersonalOperatingBlueprint
        blocks: List of block dicts

    Returns:
        Sorted list with tier and priority metadata added
    """
    scored = []
    for block in blocks:
        tier = get_tier_for_block(blueprint, block)
        behavior_key = block.get('behavior_key', '')
        pillar = _get_pillar_for_behavior(blueprint, behavior_key)
        pillar_weight = blueprint.get_pillar_weight(pillar) if pillar else 0.3

        # Priority score: lower = higher priority
        # Tier is dominant (tier * 100), then pillar weight breaks ties
        priority_score = (tier * 100) - (pillar_weight * 50)

        scored.append({
            **block,
            'tier': tier,
            'pillar': pillar,
            'pillar_weight': pillar_weight,
            'priority_score': priority_score,
        })

    return sorted(scored, key=lambda b: b['priority_score'])


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _get_pillar_for_behavior(blueprint, behavior_key):
    """Map a behavior key to its pillar."""
    # Check non-negotiables first
    nn = blueprint.non_negotiables.filter(
        behavior_key=behavior_key, is_active=True
    ).first()
    if nn and nn.pillar:
        return nn.pillar

    # Default mapping
    behavior_pillar_map = {
        'FAITH_BLOCK': 'FAITH',
        'SCRIPTURE_READING': 'FAITH',
        'PRAYER': 'FAITH',
        'MEDS_ADHERENCE': 'HEALTH_DISCIPLINE',
        'WORKOUT': 'HEALTH_DISCIPLINE',
        'NUTRITION': 'HEALTH_DISCIPLINE',
        'FASTING': 'HEALTH_DISCIPLINE',
        'WEIGHT_LOG': 'HEALTH_DISCIPLINE',
        'SLEEP': 'HEALTH_DISCIPLINE',
        'GOAL_EXECUTION': 'PURPOSE',
        'HABIT_TRACKING': 'PURPOSE',
        'JOURNAL_REFLECTION': 'REFLECTION',
        'TASK_COMPLETION': 'ORGANIZE',
        'FINANCE_REVIEW': 'ORGANIZE',
    }
    return behavior_pillar_map.get(behavior_key, '')


def _generate_recovery_plan(blueprint, block):
    """
    Generate a recovery plan for when a Tier 1 behavior is impacted.
    """
    behavior_key = block.get('behavior_key', '')
    title = block.get('title', behavior_key)

    recovery_options = {
        'WORKOUT': f"Reschedule '{title}' to later today or add compensating session tomorrow.",
        'MEDS_ADHERENCE': f"Take medication as soon as possible. Set backup reminder for +30 minutes.",
        'FAITH_BLOCK': f"Schedule abbreviated faith time today, full block tomorrow.",
        'NUTRITION': f"Adjust remaining meals to stay on plan. Log actual intake.",
        'FASTING': f"If fast broken, record it and restart with next scheduled fast.",
    }

    default_plan = (
        f"Reschedule '{title}' at the earliest available slot today. "
        f"If not possible today, prioritize it first tomorrow."
    )

    return recovery_options.get(behavior_key, default_plan)
