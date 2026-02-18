"""
Whole Life Journey - Drift Engine

Project: Whole Life Journey
Path: apps/core/blueprint/drift_engine.py
Purpose: Drift detection, scoring, and predictive risk

Description:
    Detects deviations from the user's plan and expected behaviors. Computes
    daily drift scores weighted by pillar importance. Uses PRIE for drift
    probability prediction.

    Drift types are filtered by enabled modules/features from the blueprint.

Public API:
    - record_drift_event(user, drift_type, **kwargs) -> DriftEvent
    - compute_daily_drift_score(user, date=None) -> DriftScore
    - predict_drift_probability(user) -> dict
    - get_drift_summary(user, days=7) -> dict

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging

from django.db.models import Avg, Count
from django.utils import timezone

from . import engine as blueprint_engine
from .models import DriftEvent, DriftScore

logger = logging.getLogger(__name__)


# =============================================================================
# DRIFT TYPE → PILLAR MAPPING
# =============================================================================

DRIFT_PILLAR_MAP = {
    DriftEvent.DRIFT_FAST_BREAK_EARLY: 'HEALTH_DISCIPLINE',
    DriftEvent.DRIFT_MED_MISSED: 'HEALTH_DISCIPLINE',
    DriftEvent.DRIFT_WORKOUT_SKIPPED: 'HEALTH_DISCIPLINE',
    DriftEvent.DRIFT_NUTRITION_OFF_TRACK: 'HEALTH_DISCIPLINE',
    DriftEvent.DRIFT_FAITH_BLOCK_MISSED: 'FAITH',
    DriftEvent.DRIFT_GOAL_SLIP: 'PURPOSE',
    DriftEvent.DRIFT_SLEEP_DEFICIT: 'HEALTH_DISCIPLINE',
    DriftEvent.DRIFT_BLOCK_MISSED: '',  # Generic
}

# Default severity by drift type
DRIFT_DEFAULT_SEVERITY = {
    DriftEvent.DRIFT_FAST_BREAK_EARLY: 0.6,
    DriftEvent.DRIFT_MED_MISSED: 0.8,
    DriftEvent.DRIFT_WORKOUT_SKIPPED: 0.5,
    DriftEvent.DRIFT_NUTRITION_OFF_TRACK: 0.4,
    DriftEvent.DRIFT_FAITH_BLOCK_MISSED: 0.5,
    DriftEvent.DRIFT_GOAL_SLIP: 0.4,
    DriftEvent.DRIFT_SLEEP_DEFICIT: 0.6,
    DriftEvent.DRIFT_BLOCK_MISSED: 0.3,
}


# =============================================================================
# PUBLIC API
# =============================================================================


def record_drift_event(user, drift_type, behavior_key='', severity=None,
                       description='', evidence=None, date=None):
    """
    Record a drift event. Only records if the drift type is enabled for this user.

    Args:
        user: The user
        drift_type: One of DriftEvent.DRIFT_* constants
        behavior_key: Associated behavior key
        severity: 0-1 (auto-computed if None)
        description: Human-readable description
        evidence: E3 evidence dict
        date: Date of event (default: today)

    Returns:
        DriftEvent or None (if drift type disabled)
    """
    # Check if this drift type is allowed
    enabled_types = blueprint_engine.get_enabled_drift_types(user)
    if drift_type not in enabled_types:
        logger.debug(
            "Drift type %s not enabled for %s, skipping", drift_type, user.email,
        )
        return None

    blueprint = blueprint_engine.get_blueprint(user)

    if date is None:
        date = timezone.localdate()

    if severity is None:
        severity = DRIFT_DEFAULT_SEVERITY.get(drift_type, 0.5)

    pillar = DRIFT_PILLAR_MAP.get(drift_type, '')
    tier = blueprint.get_tier_for_behavior(behavior_key) if behavior_key else 4

    event = DriftEvent.objects.create(
        user=user,
        drift_type=drift_type,
        date=date,
        behavior_key=behavior_key,
        tier=tier,
        pillar=pillar,
        severity=severity,
        description=description or f"Drift: {dict(DriftEvent.DRIFT_TYPE_CHOICES).get(drift_type, drift_type)}",
        evidence=evidence or {},
    )

    logger.info(
        "Drift event recorded: %s for %s (tier=%d, severity=%.2f)",
        drift_type, user.email, tier, severity,
    )

    # Trigger PIE insight if tier 1
    if tier == 1:
        _trigger_tier1_drift_insight(user, event)

    return event


def compute_daily_drift_score(user, date=None):
    """
    Compute the aggregate drift score for a day, weighted by pillar importance.

    Score formula:
    - Each drift event contributes: severity * pillar_weight * tier_multiplier
    - tier_multiplier: T1=3.0, T2=2.0, T3=1.5, T4=1.0
    - Score is normalized to 0-100

    Returns:
        DriftScore (created or updated)
    """
    if date is None:
        date = timezone.localdate()

    blueprint = blueprint_engine.get_blueprint(user)

    events = DriftEvent.objects.filter(user=user, date=date)
    event_count = events.count()

    if event_count == 0:
        score_obj, _ = DriftScore.objects.update_or_create(
            user=user,
            date=date,
            defaults={
                'score': 0.0,
                'event_count': 0,
                'pillar_scores': {},
            },
        )
        return score_obj

    tier_multiplier = {1: 3.0, 2: 2.0, 3: 1.5, 4: 1.0}
    pillar_scores = {}
    total_score = 0.0

    for event in events:
        pillar = event.pillar or 'UNASSIGNED'
        weight = blueprint.get_pillar_weight(pillar) if pillar != 'UNASSIGNED' else 0.3
        multiplier = tier_multiplier.get(event.tier, 1.0)
        contribution = event.severity * weight * multiplier * 10  # Scale factor

        if pillar not in pillar_scores:
            pillar_scores[pillar] = 0.0
        pillar_scores[pillar] += contribution
        total_score += contribution

    # Normalize to 0-100
    normalized_score = min(100.0, total_score)

    score_obj, _ = DriftScore.objects.update_or_create(
        user=user,
        date=date,
        defaults={
            'score': round(normalized_score, 2),
            'event_count': event_count,
            'pillar_scores': {k: round(v, 2) for k, v in pillar_scores.items()},
        },
    )

    logger.info(
        "Drift score computed for %s on %s: %.1f/100 (%d events)",
        user.email, date, normalized_score, event_count,
    )

    return score_obj


def predict_drift_probability(user):
    """
    Predict drift probability for next 24h and 72h using heuristics.

    Factors:
    - Historical failure times (pattern matching)
    - Schedule density (from architecture plan)
    - Sleep deficit (from health data)
    - Streak fatigue (consecutive days of adherence)
    - Recent drift trend

    Returns:
        dict with 'probability_24h', 'probability_72h', 'factors'
    """
    blueprint = blueprint_engine.get_blueprint(user)

    # Factor 1: Recent drift trend (last 7 days)
    seven_days_ago = timezone.localdate() - datetime.timedelta(days=7)
    recent_scores = DriftScore.objects.filter(
        user=user,
        date__gte=seven_days_ago,
    ).values_list('score', flat=True)

    avg_recent_drift = sum(recent_scores) / len(recent_scores) if recent_scores else 0
    trend_factor = min(1.0, avg_recent_drift / 50.0)  # High drift = higher probability

    # Factor 2: Schedule density
    density_factor = 0.3  # Default moderate
    from .models import ArchitecturePlan
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    plan = ArchitecturePlan.get_active_for_date(user, tomorrow)
    if plan:
        block_count = plan.blocks.count()
        density_factor = min(1.0, block_count / 12.0)  # 12+ blocks = high density

    # Factor 3: Streak fatigue
    streak_days = _count_clean_streak(user)
    # Long streaks can lead to burnout - fatigue starts after 14 days
    fatigue_factor = 0.0
    if streak_days > 14:
        fatigue_factor = min(0.5, (streak_days - 14) * 0.05)

    # Factor 4: Day of week (weekends often have more drift)
    today = timezone.localdate()
    weekend_factor = 0.2 if today.weekday() >= 4 else 0.0  # Friday+

    # Composite probability
    p_24h = min(1.0, (
        trend_factor * 0.35 +
        density_factor * 0.25 +
        fatigue_factor * 0.20 +
        weekend_factor * 0.20
    ))

    # 72h is slightly higher (more uncertainty)
    p_72h = min(1.0, p_24h * 1.3)

    factors = {
        'recent_drift_trend': round(trend_factor, 3),
        'schedule_density': round(density_factor, 3),
        'streak_fatigue': round(fatigue_factor, 3),
        'weekend_effect': round(weekend_factor, 3),
        'clean_streak_days': streak_days,
    }

    # Update today's drift score with prediction
    today_score, _ = DriftScore.objects.get_or_create(
        user=user,
        date=today,
        defaults={'score': 0.0, 'event_count': 0},
    )
    today_score.drift_probability_24h = round(p_24h, 3)
    today_score.drift_probability_72h = round(p_72h, 3)
    today_score.prediction_factors = factors
    today_score.save(update_fields=[
        'drift_probability_24h', 'drift_probability_72h',
        'prediction_factors', 'updated_at',
    ])

    return {
        'probability_24h': round(p_24h, 3),
        'probability_72h': round(p_72h, 3),
        'factors': factors,
    }


def get_drift_summary(user, days=7):
    """
    Get a drift summary for the last N days.

    Returns:
        dict with scores, events, trends
    """
    cutoff = timezone.localdate() - datetime.timedelta(days=days)

    scores = DriftScore.objects.filter(
        user=user,
        date__gte=cutoff,
    ).order_by('date')

    events = DriftEvent.objects.filter(
        user=user,
        date__gte=cutoff,
    )

    # Per-day scores
    daily_scores = [
        {'date': str(s.date), 'score': s.score, 'events': s.event_count}
        for s in scores
    ]

    # Most common drift types
    type_counts = dict(
        events.values_list('drift_type').annotate(count=Count('id'))
    )

    # Average score
    avg_score = scores.aggregate(avg=Avg('score'))['avg'] or 0

    return {
        'period_days': days,
        'average_score': round(avg_score, 1),
        'total_events': events.count(),
        'daily_scores': daily_scores,
        'drift_type_frequency': type_counts,
        'latest_prediction': predict_drift_probability(user),
    }


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _count_clean_streak(user):
    """Count consecutive days with drift score < 20 (low drift)."""
    today = timezone.localdate()
    streak = 0
    for i in range(90):  # Max lookback
        date = today - datetime.timedelta(days=i + 1)
        try:
            score = DriftScore.objects.get(user=user, date=date)
            if score.score < 20:
                streak += 1
            else:
                break
        except DriftScore.DoesNotExist:
            # No score = assume clean day
            streak += 1
    return streak


def _trigger_tier1_drift_insight(user, drift_event):
    """Trigger a PIE insight for a Tier 1 drift event."""
    try:
        from apps.core.ai_insights.insight_engine import run_insights
        event_data = {
            'event_type': 'tier1_drift',
            'module': 'blueprint',
            'action': 'drift_detected',
            'record_id': drift_event.pk,
            'context': {
                'drift_type': drift_event.drift_type,
                'behavior_key': drift_event.behavior_key,
                'tier': drift_event.tier,
                'severity': drift_event.severity,
            },
        }
        run_insights(user, event_data)
    except Exception as e:
        logger.warning("Failed to trigger PIE insight for drift: %s", e)
