"""
Whole Life Journey — Predictive Interventions Engine

Project: Whole Life Journey
Path: apps/core/blueprint/predictive_interventions.py
Purpose: Auto-generate CoS interventions from PRIE+PIE+PGE signals

Description:
    Combines signals from three intelligence engines to proactively create
    interventions BEFORE drift occurs:

    - PRIE (Predictive Intelligence Engine): Trajectory projection
    - PIE (Proactive Insight Engine): Event-driven factual insights
    - PGE (Proactive Guidance Engine): Evidence-based guidance

    When combined signals exceed thresholds, the engine creates
    appropriately-leveled interventions via the intervention engine.

Public API:
    - evaluate_predictive_signals(user) -> list[InterventionLog]
    - get_proactive_message(user) -> str or None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# THRESHOLDS
# =============================================================================

# Drift probability thresholds for intervention
DRIFT_THRESHOLD_NUDGE = 0.25       # 25% → gentle reminder
DRIFT_THRESHOLD_PING = 0.45        # 45% → proactive ping
DRIFT_THRESHOLD_INTERRUPT = 0.65   # 65% → interrupt with evidence


# =============================================================================
# PUBLIC API
# =============================================================================


def evaluate_predictive_signals(user):
    """
    Evaluate combined PRIE+PIE+PGE signals and create interventions
    when thresholds are exceeded.

    This is called by the ISE assistant_triggers runner periodically.

    Args:
        user: Django User instance.

    Returns:
        list of InterventionLog instances created (may be empty).
    """
    from .intervention_engine import create_intervention, get_pending_interventions
    from .intervention_intensity import compute_intensity
    from .models import InterventionLog

    interventions = []

    # Don't pile on if there are already pending interventions
    pending = get_pending_interventions(user)
    if pending.filter(trigger_type__in=[
        'high_drift_probability', 'predictive_insight', 'predictive_guidance',
    ]).exists():
        return interventions

    # Gather signals
    signals = _gather_signals(user)

    # Signal 1: High drift probability (from PRIE / drift engine)
    drift_24h = signals.get('drift_probability_24h', 0)

    if drift_24h >= DRIFT_THRESHOLD_INTERRUPT:
        intensity = compute_intensity(user)
        msg = _build_drift_intervention_message(user, drift_24h, signals)
        intervention = create_intervention(
            user=user,
            level=min(intensity.escalation_level, InterventionLog.LEVEL_INTERRUPT),
            trigger_type='high_drift_probability',
            message=msg,
            evidence={
                'drift_probability_24h': drift_24h,
                'intensity_level': intensity.level,
                'factors': signals.get('drift_factors', {}),
            },
            delivered_via='in_app',
        )
        interventions.append(intervention)

    elif drift_24h >= DRIFT_THRESHOLD_PING:
        msg = _build_drift_warning_message(user, drift_24h, signals)
        intervention = create_intervention(
            user=user,
            level=InterventionLog.LEVEL_PING,
            trigger_type='high_drift_probability',
            message=msg,
            evidence={
                'drift_probability_24h': drift_24h,
                'factors': signals.get('drift_factors', {}),
            },
            delivered_via='in_app',
        )
        interventions.append(intervention)

    elif drift_24h >= DRIFT_THRESHOLD_NUDGE:
        msg = _build_drift_nudge_message(drift_24h)
        intervention = create_intervention(
            user=user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='high_drift_probability',
            message=msg,
            delivered_via='in_app',
        )
        interventions.append(intervention)

    # Signal 2: PIE insight signals (recent insights with high severity)
    pie_signals = signals.get('high_severity_insights', [])
    for insight in pie_signals[:1]:  # Max 1 insight-driven intervention
        msg = f"Insight: {insight.get('summary', 'Pattern detected that needs attention.')}"
        intervention = create_intervention(
            user=user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='predictive_insight',
            message=msg,
            evidence=insight,
            delivered_via='in_app',
        )
        interventions.append(intervention)

    # Signal 3: PGE guidance signals (urgent guidance not yet acted on)
    pge_signals = signals.get('urgent_guidance', [])
    for guidance in pge_signals[:1]:  # Max 1 guidance-driven intervention
        msg = f"Recommendation: {guidance.get('title', 'Action recommended.')}"
        intervention = create_intervention(
            user=user,
            level=InterventionLog.LEVEL_NUDGE,
            trigger_type='predictive_guidance',
            message=msg,
            evidence={'guidance_id': guidance.get('id')},
            delivered_via='in_app',
        )
        interventions.append(intervention)

    if interventions:
        logger.info(
            "Predictive interventions for %s: %d created (drift=%.0f%%)",
            user.email, len(interventions), drift_24h * 100,
        )

    return interventions


def get_proactive_message(user):
    """
    Generate a proactive CoS message if conditions warrant one.

    Returns a formatted message string or None if no message needed.

    Args:
        user: Django User instance.

    Returns:
        str or None
    """
    signals = _gather_signals(user)
    drift_24h = signals.get('drift_probability_24h', 0)

    if drift_24h < DRIFT_THRESHOLD_NUDGE:
        return None

    from apps.core.ai_orchestrator.briefing_formatter import build_intervention_briefing

    return build_intervention_briefing(
        trigger_type='predictive',
        message=_build_drift_warning_message(user, drift_24h, signals),
        evidence={'drift_probability_24h': drift_24h},
        alignment_score=signals.get('alignment_score'),
        recommendation=_get_recommendation(drift_24h),
    )


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _gather_signals(user):
    """Gather signals from PRIE, PIE, and PGE."""
    signals = {
        'drift_probability_24h': 0,
        'drift_probability_72h': 0,
        'drift_factors': {},
        'high_severity_insights': [],
        'urgent_guidance': [],
        'alignment_score': 100,
    }

    # PRIE / Drift predictions
    try:
        from . import drift_engine
        prediction = drift_engine.predict_drift_probability(user)
        signals['drift_probability_24h'] = prediction.get('probability_24h', 0)
        signals['drift_probability_72h'] = prediction.get('probability_72h', 0)
        signals['drift_factors'] = prediction.get('factors', {})
    except Exception as e:
        logger.debug("Predictive: drift prediction failed: %s", e)

    # Alignment score
    try:
        from .alignment_engine import compute_alignment_score
        alignment = compute_alignment_score(user)
        signals['alignment_score'] = alignment.score
    except Exception:
        pass

    # PIE insights (recent high-severity)
    try:
        from apps.core.ai_insights.models import InsightEntry
        recent = InsightEntry.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timezone.timedelta(hours=24),
            severity__gte=0.7,
            is_read=False,
        ).values('summary', 'insight_type', 'severity')[:3]
        signals['high_severity_insights'] = list(recent)
    except Exception:
        pass

    # PGE guidance (urgent unacted)
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        urgent = GuidanceItem.objects.filter(
            user=user,
            is_active=True,
            priority__gte=8,
            is_acted_on=False,
        ).values('id', 'title', 'priority')[:3]
        signals['urgent_guidance'] = list(urgent)
    except Exception:
        pass

    return signals


def _build_drift_intervention_message(user, drift_24h, signals):
    """Build an intervention message for high drift probability."""
    pct = round(drift_24h * 100)
    factors = signals.get('drift_factors', {})

    parts = [f"24-hour drift probability is at {pct}%."]

    if factors.get('recent_drift_trend', 0) > 0.5:
        parts.append("Recent drift trend is elevated.")
    if factors.get('schedule_density', 0) > 0.7:
        parts.append("Tomorrow's schedule is dense.")
    if factors.get('streak_fatigue', 0) > 0.2:
        clean_days = factors.get('clean_streak_days', 0)
        parts.append(f"Streak fatigue after {clean_days} consecutive days.")

    alignment = signals.get('alignment_score', 100)
    if alignment < 80:
        parts.append(f"Current alignment is {round(alignment)}%.")

    return " ".join(parts)


def _build_drift_warning_message(user, drift_24h, signals):
    """Build a warning-level drift message."""
    pct = round(drift_24h * 100)
    return (
        f"Drift risk is building ({pct}% probability in next 24h). "
        f"Consider reviewing your protected commitments."
    )


def _build_drift_nudge_message(drift_24h):
    """Build a nudge-level drift message."""
    pct = round(drift_24h * 100)
    return f"Drift probability is {pct}%. Stay focused on Tier-1 priorities."


def _get_recommendation(drift_24h):
    """Get a recommendation based on drift probability."""
    if drift_24h >= DRIFT_THRESHOLD_INTERRUPT:
        return "Review and lock your Tier-1 commitments immediately."
    elif drift_24h >= DRIFT_THRESHOLD_PING:
        return "Consider simplifying tomorrow's plan to protect core behaviors."
    else:
        return "Monitor closely. No immediate action required."
