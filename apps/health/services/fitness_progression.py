# ==============================================================================
# File: fitness_progression.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic weight progression — detects plateaus per exercise
#              and recommends +5 lb increases. Read-only: never modifies stored data.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-27
# ==============================================================================
"""
Fitness Progression Service — Deterministic plateau detection and weight recommendation.

For each exercise, examines the last 3 completed sessions containing that exercise.
If the max working weight (non-warmup) is consistent across all 3 (within ±5 lbs),
recommends a +5 lb increase. Otherwise returns the most recent weight unchanged.

This service is consumed at workout prefill time only. It never modifies
WorkoutSession, ExerciseSet, or template records.
"""

import logging
from decimal import Decimal

from django.db.models import Max

logger = logging.getLogger(__name__)

PROGRESSION_INCREMENT = Decimal("5")
PLATEAU_TOLERANCE = Decimal("5")
REQUIRED_SESSIONS = 3


def get_recommended_weight(user, exercise_id):
    """
    Determine recommended weight for an exercise based on plateau detection.

    Args:
        user: Django User instance.
        exercise_id: PK of the Exercise.

    Returns:
        dict with 'weight' (float) and 'progression' sub-dict, or None if
        no weight history exists for this exercise.
    """
    from apps.health.models import ExerciseSet, WorkoutSession

    # Query 1: last 3 completed sessions containing this exercise
    session_ids = list(
        WorkoutSession.objects.filter(
            user=user,
            completed_at__isnull=False,
            workout_exercises__exercise_id=exercise_id,
        )
        .order_by("-completed_at")
        .values_list("pk", flat=True)
        .distinct()[:REQUIRED_SESSIONS]
    )

    if not session_ids:
        return None

    # Query 2: max non-warmup weight per session (batched)
    weight_by_session = dict(
        ExerciseSet.objects.filter(
            workout_exercise__exercise_id=exercise_id,
            workout_exercise__session_id__in=session_ids,
            is_warmup=False,
            weight__isnull=False,
            weight__gt=0,
        )
        .values_list("workout_exercise__session_id")
        .annotate(max_weight=Max("weight"))
        .values_list("workout_exercise__session_id", "max_weight")
    )

    if not weight_by_session:
        return None

    # Order weights by session recency (session_ids is already ordered)
    ordered_weights = [weight_by_session[sid] for sid in session_ids if sid in weight_by_session]

    if not ordered_weights:
        return None

    last_weight = ordered_weights[0]  # most recent session

    # Need at least REQUIRED_SESSIONS with weight data to detect plateau
    if len(ordered_weights) < REQUIRED_SESSIONS:
        return {
            "weight": float(last_weight),
            "progression": {
                "applied": False,
                "increase": 0,
                "reason": None,
            },
        }

    # Plateau check: all weights within ±PLATEAU_TOLERANCE of each other
    weight_spread = max(ordered_weights) - min(ordered_weights)
    plateau_detected = weight_spread <= PLATEAU_TOLERANCE

    if plateau_detected:
        recommended = last_weight + PROGRESSION_INCREMENT
        return {
            "weight": float(recommended),
            "progression": {
                "applied": True,
                "increase": float(PROGRESSION_INCREMENT),
                "reason": "plateau_3_sessions",
            },
        }

    return {
        "weight": float(last_weight),
        "progression": {
            "applied": False,
            "increase": 0,
            "reason": None,
        },
    }
