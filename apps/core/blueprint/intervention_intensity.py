"""
Whole Life Journey — Adaptive Discipline Engine

Project: Whole Life Journey
Path: apps/core/blueprint/intervention_intensity.py
Purpose: Dynamically compute intervention intensity level (1-5) from user context

Description:
    Implements a 5-level adaptive discipline model that determines how
    aggressively the CoS should intervene based on real-time user state.

    Levels:
        1 — Gentle Reminder: Low-friction text nudge
        2 — Prompt: Clear call-to-action with evidence
        3 — Evidence Forecast: Show projected consequence if behavior continues
        4 — Friction Gate: Require explicit confirmation to proceed
        5 — Hard Block: Lock out action until recovery plan accepted

    Factors:
        - Drift probability (24h)
        - Override frequency (14d)
        - Tier of affected behavior
        - Schedule density (capacity %)
        - Biological risk (fasting, medication adherence)

Public API:
    - compute_intensity(user, behavior_key=None, context=None) -> IntensityResult
    - INTENSITY_LEVELS: dict of level definitions

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# INTENSITY LEVEL DEFINITIONS
# =============================================================================

INTENSITY_LEVELS = {
    1: {
        'name': 'Gentle Reminder',
        'description': 'Low-friction text nudge in the panel',
        'escalation_level': 1,  # maps to InterventionLog.LEVEL_NUDGE
    },
    2: {
        'name': 'Prompt',
        'description': 'Clear call-to-action with supporting evidence',
        'escalation_level': 1,  # still nudge, but with richer content
    },
    3: {
        'name': 'Evidence Forecast',
        'description': 'Show projected consequence if current behavior continues',
        'escalation_level': 2,  # maps to LEVEL_PING
    },
    4: {
        'name': 'Friction Gate',
        'description': 'Require explicit confirmation before proceeding',
        'escalation_level': 4,  # maps to LEVEL_FRICTION_GATE
    },
    5: {
        'name': 'Hard Block',
        'description': 'Lock action until recovery plan is accepted',
        'escalation_level': 4,  # friction gate + recovery requirement
    },
}


@dataclass
class IntensityResult:
    """Result of intensity computation."""
    level: int
    name: str
    escalation_level: int
    score: float  # 0-100 composite risk score
    factors: dict
    recommendation: str


# =============================================================================
# PUBLIC API
# =============================================================================


def compute_intensity(user, behavior_key=None, context=None):
    """
    Compute the adaptive discipline intensity level for the current situation.

    The intensity is computed from a weighted composite of risk factors.
    Higher risk = more aggressive intervention.

    Args:
        user: Django User instance.
        behavior_key: Optional specific behavior being evaluated.
        context: Optional pre-built CoS context dict. If None, built fresh.

    Returns:
        IntensityResult with level (1-5), factors, and recommendation.
    """
    if context is None:
        try:
            from apps.core.ai_orchestrator.cos_context import build_cos_context
            context = build_cos_context(user)
        except Exception:
            context = {}

    factors = {}
    score = 0.0

    # Factor 1: Drift probability (24h) — weight 30%
    drift_p = context.get('drift_probability', {})
    drift_24h = drift_p.get('probability_24h', 0)
    drift_factor = min(1.0, drift_24h / 100.0)
    factors['drift_probability_24h'] = drift_24h
    score += drift_factor * 30.0

    # Factor 2: Override frequency (14d) — weight 20%
    overrides = context.get('override_frequency_14d', 0)
    override_factor = min(1.0, overrides / 10.0)  # 10+ overrides = max
    factors['override_frequency_14d'] = overrides
    score += override_factor * 20.0

    # Factor 3: Tier of behavior — weight 20%
    tier = _get_behavior_tier(user, behavior_key)
    tier_factor = {1: 1.0, 2: 0.6, 3: 0.3, 4: 0.1}.get(tier, 0.3)
    factors['behavior_tier'] = tier
    score += tier_factor * 20.0

    # Factor 4: Schedule density (capacity %) — weight 15%
    capacity = context.get('capacity_snapshot', {}).get('capacity_pct', 0)
    density_factor = min(1.0, capacity / 90.0)  # 90%+ = max density
    factors['capacity_pct'] = capacity
    score += density_factor * 15.0

    # Factor 5: Biological risk (fasting + medication) — weight 15%
    bio_risk = 0.0
    fast = context.get('active_fast_status', {})
    if fast.get('active'):
        bio_risk += 0.5  # Active fast = elevated risk

    med = context.get('medication_adherence_state', {})
    if med:
        adherence = med.get('adherence_pct', 100)
        if adherence < 80:
            bio_risk += (100 - adherence) / 100.0
    bio_risk = min(1.0, bio_risk)
    factors['biological_risk'] = round(bio_risk, 2)
    score += bio_risk * 15.0

    # Compute level from composite score
    score = min(100.0, score)
    factors['composite_score'] = round(score, 1)

    if score >= 80:
        level = 5
    elif score >= 60:
        level = 4
    elif score >= 40:
        level = 3
    elif score >= 20:
        level = 2
    else:
        level = 1

    # Tier-1 override: always at least level 4 for Tier-1 violations
    if tier == 1 and score >= 30:
        level = max(level, 4)

    level_def = INTENSITY_LEVELS[level]
    recommendation = _build_recommendation(level, factors)

    return IntensityResult(
        level=level,
        name=level_def['name'],
        escalation_level=level_def['escalation_level'],
        score=round(score, 1),
        factors=factors,
        recommendation=recommendation,
    )


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _get_behavior_tier(user, behavior_key):
    """Look up the tier for a behavior key from the blueprint."""
    if not behavior_key:
        return 4

    try:
        from . import engine as blueprint_engine
        blueprint = blueprint_engine.get_blueprint(user)
        return blueprint.get_tier_for_behavior(behavior_key)
    except Exception:
        return 4


def _build_recommendation(level, factors):
    """Build a human-readable recommendation based on intensity level."""
    if level == 5:
        return (
            "High-risk pattern detected. Recommend blocking until recovery "
            "plan is reviewed. Override frequency and drift are elevated."
        )
    elif level == 4:
        return (
            "Protected behavior at risk. Recommend friction gate before "
            "allowing deviation. Show identity cost and adherence projection."
        )
    elif level == 3:
        parts = []
        if factors.get('drift_probability_24h', 0) > 30:
            parts.append(f"24h drift risk at {factors['drift_probability_24h']}%")
        if factors.get('override_frequency_14d', 0) > 3:
            parts.append(f"{factors['override_frequency_14d']} overrides in 14 days")
        evidence = ". ".join(parts) if parts else "Moderate risk detected"
        return f"Recommend evidence forecast. {evidence}."
    elif level == 2:
        return "Recommend clear prompt with supporting data."
    else:
        return "Low risk. Gentle reminder is sufficient."
