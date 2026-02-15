"""
PIL — Persona Adaptation.

Calculates tone intensity (0.6-1.4) based on GLOE responsiveness,
ICQG usefulness, SAE state severity, and message context.

All database queries happen in this module. The renderer receives
only pre-computed values.

Project: Whole Life Journey
Path: apps/core/ai_persona/persona_adaptation.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

logger = logging.getLogger(__name__)

# Intensity bounds
MIN_INTENSITY = 0.6
MAX_INTENSITY = 1.4
DEFAULT_INTENSITY = 1.0

# Factor weights (must sum to 1.0)
WEIGHT_GLOE = 0.30
WEIGHT_ICQG = 0.20
WEIGHT_SEVERITY = 0.20
WEIGHT_PRIORITY = 0.30


def calculate_tone_intensity(user, persona_key, context):
    """
    Calculate how intensely the persona voice should be applied.

    Args:
        user: Django User instance.
        persona_key: Coaching style key (unused currently, reserved for
                     per-style sensitivity scaling).
        context: dict with optional keys:
            - priority: int (1-5, from PGE)
            - message_type: str ("guidance", "briefing", "weekly_report")
            - domain: str (module name)
            - severity: str (from insight)

    Returns:
        float between 0.6 and 1.4.
    """
    try:
        gloe_factor = _get_gloe_factor(user)
        icqg_factor = _get_icqg_factor(user)
        severity_factor = _get_severity_factor(user)
        priority_factor = _get_priority_factor(context)

        # Weighted average
        intensity = (
            WEIGHT_GLOE * gloe_factor
            + WEIGHT_ICQG * icqg_factor
            + WEIGHT_SEVERITY * severity_factor
            + WEIGHT_PRIORITY * priority_factor
        )

        # Clamp to bounds
        intensity = max(MIN_INTENSITY, min(MAX_INTENSITY, intensity))

        return round(intensity, 2)

    except Exception as e:
        logger.warning(f"PIL: Tone intensity calculation failed: {e}")
        return DEFAULT_INTENSITY


def _get_gloe_factor(user):
    """
    Map GLOE responsiveness score to intensity factor.

    < 0.3 → 0.6 (user not engaging → soften persona)
    0.3-0.7 → linear scale 0.8-1.0
    > 0.7 → linear scale 1.0-1.3 (user engaged → can strengthen)
    Default (no data): 1.0
    """
    try:
        from apps.core.ai_guidance_learning.learning_engine import (
            get_responsiveness_score,
        )

        score = get_responsiveness_score(user)
    except Exception:
        return DEFAULT_INTENSITY

    if score < 0.3:
        # Linear: 0.0 → 0.6, 0.3 → 0.8
        return 0.6 + (score / 0.3) * 0.2
    elif score <= 0.7:
        # Linear: 0.3 → 0.8, 0.7 → 1.0
        return 0.8 + ((score - 0.3) / 0.4) * 0.2
    else:
        # Linear: 0.7 → 1.0, 1.0 → 1.3
        return 1.0 + ((score - 0.7) / 0.3) * 0.3


def _get_icqg_factor(user):
    """
    Map ICQG usefulness to intensity factor.

    Computes average usefulness_score from last 4 weeks of
    QualityMetricAggregate records.

    Low usefulness (< 0.3) → 0.7 (quality is low, soften approach)
    Medium (0.3-0.7) → 1.0
    High (> 0.7) → 1.1
    Default (no data): 1.0
    """
    try:
        from apps.core.ai_quality.quality_models import QualityMetricAggregate
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now().date() - timedelta(weeks=4)

        aggregates = QualityMetricAggregate.objects.filter(
            week_start__gte=cutoff,
        ).values_list("usefulness_score", flat=True)

        if not aggregates:
            return DEFAULT_INTENSITY

        avg_score = sum(aggregates) / len(aggregates)
    except Exception:
        return DEFAULT_INTENSITY

    if avg_score < 0.3:
        return 0.7
    elif avg_score <= 0.7:
        return DEFAULT_INTENSITY
    else:
        return 1.1


def _get_severity_factor(user):
    """
    Infer severity from SAE state.

    Checks state indicators for conditions that warrant stronger messaging.
    Takes the max of all applicable factors.

    Default (no concerning state): 1.0
    """
    try:
        from apps.core.ai_state.state_engine import get_user_state

        state = get_user_state(user)
        if not state:
            return DEFAULT_INTENSITY
    except Exception:
        return DEFAULT_INTENSITY

    factor = DEFAULT_INTENSITY

    # Goals: overdue goals increase severity
    goals = state.get("goals", {})
    overdue = goals.get("overdue_goal_count", 0)
    if overdue and overdue > 3:
        factor = max(factor, 1.2)
    elif overdue and overdue > 0:
        factor = max(factor, 1.1)

    # Health: concerning trends
    health = state.get("health", {})
    weight_trend = health.get("weight_trend", "")
    if weight_trend == "increasing":
        factor = max(factor, 1.1)

    # Journal: long absence
    journal = state.get("journal", {})
    days_since = journal.get("days_since_entry")
    if days_since and days_since > 7:
        factor = max(factor, 1.1)

    # Habits: low completion
    habits = state.get("habits", {})
    completion = habits.get("avg_completion_rate")
    if completion is not None and completion < 0.3:
        factor = max(factor, 1.1)

    return factor


def _get_priority_factor(context):
    """
    Map message priority/type to intensity factor.

    Priority 1 (critical) → 1.3
    Priority 2 (high) → 1.1
    Priority 3 (medium) → 1.0
    Priority 4-5 (low/info) → 0.9
    message_type == "briefing" → 0.95 (briefings should be calmer)
    message_type == "weekly_report" → 0.9 (reports are reflective)
    """
    if not context:
        return DEFAULT_INTENSITY

    priority = context.get("priority")
    message_type = context.get("message_type", "")

    # Priority takes precedence if available
    if priority is not None:
        if priority <= 1:
            return 1.3
        elif priority == 2:
            return 1.1
        elif priority == 3:
            return DEFAULT_INTENSITY
        else:
            return 0.9

    # Fall back to message type
    if message_type == "briefing":
        return 0.95
    elif message_type == "weekly_report":
        return 0.9

    return DEFAULT_INTENSITY
