"""
Whole Life Journey — Alignment Score Engine

Project: Whole Life Journey
Path: apps/core/blueprint/alignment_engine.py
Purpose: Compute weighted blueprint alignment score

Description:
    Computes a 0-100 alignment score representing how well the user's
    actual behavior matches their declared blueprint.

    Weights:
        - Tier 1 (protected): 50% of total score
        - Tier 2 (strategic): 30% of total score
        - Tier 3 (supportive): 20% of total score

    Factors per tier:
        - Block completion rate
        - Drift event frequency
        - Override frequency
        - Adherence to scheduled times

Public API:
    - compute_alignment_score(user, date=None) -> AlignmentResult
    - get_alignment_trend(user, days=7) -> list[dict]

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
from dataclasses import dataclass
from typing import List, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# TIER WEIGHTS
# =============================================================================

TIER_WEIGHTS = {
    1: 0.50,  # Protected commitments = 50%
    2: 0.30,  # Strategic focus = 30%
    3: 0.20,  # Supportive activities = 20%
    4: 0.00,  # Buffer/flexible = not scored
}


@dataclass
class AlignmentResult:
    """Result of alignment score computation."""
    score: float  # 0-100
    tier_scores: dict  # {tier: score}
    tier_weights: dict  # {tier: weight}
    factors: dict
    grade: str  # A, B, C, D, F


# =============================================================================
# PUBLIC API
# =============================================================================


def compute_alignment_score(user, date=None):
    """
    Compute the weighted alignment score for a given date.

    The score reflects how closely the user's actions match their
    blueprint for the day. Each tier contributes proportionally
    to its weight.

    Args:
        user: Django User instance.
        date: Target date (default: today).

    Returns:
        AlignmentResult with score, breakdown, and grade.
    """
    from .models import ArchitecturePlan, DriftEvent, InterventionLog

    if date is None:
        date = timezone.localdate()

    tier_scores = {1: 100.0, 2: 100.0, 3: 100.0, 4: 100.0}
    factors = {
        'date': str(date),
        'has_plan': False,
        'block_completion': {},
        'drift_events': {},
        'override_count': 0,
    }

    # Get the plan for this date
    plan = ArchitecturePlan.get_active_for_date(user, date)
    if not plan:
        # No plan = baseline score (assume perfect if nothing was planned)
        return AlignmentResult(
            score=100.0,
            tier_scores=tier_scores,
            tier_weights=TIER_WEIGHTS,
            factors=factors,
            grade='A',
        )

    factors['has_plan'] = True
    blocks = list(plan.blocks.all())

    # Group blocks by tier
    tier_blocks = {1: [], 2: [], 3: [], 4: []}
    for block in blocks:
        tier = block.tier if block.tier in tier_blocks else 4
        tier_blocks[tier].append(block)

    # Compute per-tier completion rate
    for tier, tier_block_list in tier_blocks.items():
        if not tier_block_list:
            tier_scores[tier] = 100.0  # No blocks = perfect
            continue

        completed = sum(1 for b in tier_block_list if b.is_completed)
        total = len(tier_block_list)
        completion_rate = (completed / total * 100) if total > 0 else 100

        factors['block_completion'][f'tier_{tier}'] = {
            'completed': completed,
            'total': total,
            'rate': round(completion_rate, 1),
        }

        tier_scores[tier] = completion_rate

    # Factor in drift events (reduces score)
    drift_events = DriftEvent.objects.filter(user=user, date=date)
    for event in drift_events:
        tier = event.tier if event.tier in tier_scores else 4
        # Each drift event reduces tier score by severity * 10
        penalty = event.severity * 10
        tier_scores[tier] = max(0, tier_scores[tier] - penalty)

    drift_count = drift_events.count()
    factors['drift_events'] = {'count': drift_count}

    # Factor in overrides (reduces Tier-1 score specifically)
    day_start = timezone.make_aware(
        datetime.datetime.combine(date, datetime.time.min)
    )
    day_end = timezone.make_aware(
        datetime.datetime.combine(date, datetime.time.max)
    )
    overrides = InterventionLog.objects.filter(
        user=user,
        user_response='proceeded',
        created_at__range=(day_start, day_end),
    ).count()

    if overrides > 0:
        # Each override reduces Tier-1 by 15 points
        tier_scores[1] = max(0, tier_scores[1] - overrides * 15)
        factors['override_count'] = overrides

    # Compute weighted score
    weighted_score = 0.0
    for tier, weight in TIER_WEIGHTS.items():
        weighted_score += tier_scores[tier] * weight

    weighted_score = round(min(100.0, max(0.0, weighted_score)), 1)

    # Assign grade
    if weighted_score >= 90:
        grade = 'A'
    elif weighted_score >= 80:
        grade = 'B'
    elif weighted_score >= 65:
        grade = 'C'
    elif weighted_score >= 50:
        grade = 'D'
    else:
        grade = 'F'

    return AlignmentResult(
        score=weighted_score,
        tier_scores={k: round(v, 1) for k, v in tier_scores.items()},
        tier_weights=TIER_WEIGHTS,
        factors=factors,
        grade=grade,
    )


def get_alignment_trend(user, days=7):
    """
    Get alignment scores for the last N days.

    Args:
        user: Django User instance.
        days: Number of days to look back.

    Returns:
        list of dicts with date, score, and grade.
    """
    today = timezone.localdate()
    trend = []

    for i in range(days):
        date = today - datetime.timedelta(days=i)
        try:
            result = compute_alignment_score(user, date)
            trend.append({
                'date': str(date),
                'score': result.score,
                'grade': result.grade,
                'tier_scores': result.tier_scores,
            })
        except Exception as e:
            logger.debug("Alignment trend: failed for %s on %s: %s", user.email, date, e)
            trend.append({
                'date': str(date),
                'score': 100.0,
                'grade': 'A',
                'tier_scores': {},
            })

    return list(reversed(trend))  # Oldest first
